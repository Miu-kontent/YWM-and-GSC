import json
import os
import sys
import time
import requests

DEBUG = False

BASE_URL = "https://api-metrika.yandex.net"


def log(msg):
    if DEBUG:
        print(f'[DEBUG] {msg}')


def log_api(method, url, status, body=None):
    if DEBUG:
        log(f'{method} {url} → {status}')
        if body is not None:
            log(f'  body: {json.dumps(body, ensure_ascii=False)[:500]}')


def load_script_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    arrays_dir = os.path.join(script_dir, '..', 'arrays')
    data_file = os.path.join(arrays_dir, 'yandex_metrika_add_mirrors.json')
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def normalize_host(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def api_request(method, url, headers, json_body=None, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            log_api(method, url, resp.status_code)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            log_api(method, url, resp.status_code, body)
            return resp.status_code, body, None
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return None, None, f"Соединение не установлено после {retries} попыток"
            time.sleep(1)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, None, f"Превышен таймаут ({timeout}с) после {retries} попыток"
            time.sleep(1)
        except Exception as e:
            return None, None, str(e)
    return None, None, "Unknown error"


def mirror_key(m):
    if isinstance(m, dict):
        return (m.get("site") or m.get("domain") or "").strip().lower()
    return str(m).strip().lower()


def mirror_status(m):
    if isinstance(m, dict):
        return m.get("status", "")
    return ""


def main():
    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить')
        return

    metric_id = config.get('metric_id')
    if not metric_id:
        print('⚠️  Для запуска скрипта не хватает данных: metric_id')
        print('ℹ️  Получите номер счётчика кнопкой "Получить" на вкладке Яндекс → Ключи')
        return

    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        sites = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        sites = [str(l).strip() for l in links_raw if str(l).strip()]
    else:
        sites = []

    if not sites:
        print('❌ Нет сайтов для добавления!')
        return

    headers = {
        'Authorization': f'OAuth {token}',
        'Content-Type': 'application/json'
    }

    log(f'token: {token[:20]}...')
    log(f'metric_id: {metric_id}')
    log(f'Сайтов: {len(sites)}')
    log(f'Список: {sites}')

    print(f'ℹ️  Счётчик: {metric_id}')
    print(f'ℹ️  Сайтов к добавлению: {len(sites)}')

    print(f'ℹ️  Получаю зеркала счётчика...')
    status, counter_data, err = api_request(
        'GET',
        f'{BASE_URL}/management/v1/counter/{metric_id}',
        headers
    )
    if err:
        print(f'⚠️  Ошибка получения данных счётчика: {err}')
        return
    if status != 200:
        error_msg = counter_data.get('message', f'HTTP {status}') if isinstance(counter_data, dict) else f'HTTP {status}'
        print(f'⚠️  Ошибка получения данных счётчика: {error_msg}')
        return

    counter = counter_data.get('counter', {}) if isinstance(counter_data, dict) else {}
    mirrors = counter.get('mirrors', []) or []
    mirrors2 = counter.get('mirrors2', []) or []
    log(f'Получено зеркал (mirrors): {len(mirrors)}')
    log(f'Получено зеркал (mirrors2): {len(mirrors2)}')

    existing_status = {}
    for m in mirrors2:
        key = mirror_key(m)
        if key:
            existing_status[key] = mirror_status(m)
    for m in mirrors:
        key = mirror_key(m)
        if key and key not in existing_status:
            existing_status[key] = ""

    active_mirrors = list(mirrors)

    def build_mirror_item(site):
        if active_mirrors and isinstance(active_mirrors[0], dict):
            return {"site": site}
        return site

    already_count = 0
    added_count = 0
    error_count = 0

    for i, site in enumerate(sites, 1):
        hostname = normalize_host(site)
        print(f'🔄 [{i}/{len(sites)}] {site}')

        if hostname in existing_status:
            status_label = existing_status[hostname]
            status_map = {
                "": "✅ Добавлен ранее",
                "need_webmaster_confirm": "⚠️ Ожидает подтверждения",
                "ok": "⭐ Привязан ранее",
            }
            row_status = status_map.get(status_label, f"ℹ️ Уже добавлено ({status_label})")
            already_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, row_status]}, ensure_ascii=False)}')
            time.sleep(0.3)
            continue

        new_mirror = build_mirror_item(hostname)
        put_body = {"counter": {"mirrors": active_mirrors + [new_mirror]}}

        put_status, put_body_data, put_err = api_request(
            'PUT',
            f'{BASE_URL}/management/v1/counter/{metric_id}',
            headers,
            json_body=put_body
        )

        if put_err:
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {put_err}"]}, ensure_ascii=False)}')
        elif put_status == 200:
            added_count += 1
            active_mirrors.append(new_mirror)
            existing_status[hostname] = ""
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "✅ Добавлен"]}, ensure_ascii=False)}')
        else:
            error_code = put_body_data.get('code', f'HTTP {put_status}') if isinstance(put_body_data, dict) else f'HTTP {put_status}'
            error_message = put_body_data.get('message', '') if isinstance(put_body_data, dict) else ''
            error_detail = f"{error_message} ({error_code})" if error_message else str(error_code)
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {error_detail}"]}, ensure_ascii=False)}')

    print()
    summary = {
        "Всего": len(sites),
        "Добавлено ранее": already_count,
        "Добавлено": added_count,
        "Ошибок": error_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()