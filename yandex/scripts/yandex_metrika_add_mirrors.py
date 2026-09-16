import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

DEBUG = False

BASE_URL = "https://api-metrika.yandex.net"
DEFAULT_BATCH_SIZE = 50


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
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


from yandex_client import load_config


def normalize_host(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def api_request(method, url, headers, json_body=None, retries=5, timeout=90):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            log_api(method, url, resp.status_code)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            log_api(method, url, resp.status_code, body)
            if resp.status_code in (500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2)
                continue
            return resp.status_code, body, None
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return None, None, f"Соединение не установлено после {retries} попыток"
            time.sleep(2)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, None, f"Превышен таймаут ({timeout}с) после {retries} попыток"
            time.sleep(2)
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


def put_error_str(put_status, put_body_data):
    error_code = put_body_data.get('code', f'HTTP {put_status}') if isinstance(put_body_data, dict) else f'HTTP {put_status}'
    error_message = put_body_data.get('message', '') if isinstance(put_body_data, dict) else ''
    return f"{error_message} ({error_code})" if error_message else str(error_code)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

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
        'Authorization': f'OAuth {token}'
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

    pending_additions = []
    for site in sites:
        hostname = normalize_host(site)
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
            continue
        pending_additions.append(hostname)

    if not pending_additions:
        print()
        summary = {
            "Всего": len(sites),
            "Добавлено ранее": already_count,
            "Добавлено": 0,
            "Ошибок": 0
        }
        print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
        print('__TABLE_DONE__:{}')
        return

    batch_size = DEFAULT_BATCH_SIZE
    processed = 0
    total = len(pending_additions)
    i = 0

    print(f'ℹ️  Список новых сайтов: {len(pending_additions)}')
    print(f'ℹ️  Пакетная вставка (по {batch_size}, с авто-уменьшением при ошибках)...')

    def put_batch(batch):
        put_body = {"counter": {"mirrors": active_mirrors + [build_mirror_item(s) for s in batch]}}
        result = api_request(
            'PUT',
            f'{BASE_URL}/management/v1/counter/{metric_id}',
            headers,
            json_body=put_body,
            retries=5,
            timeout=90
        )
        return result, put_body

    while i < len(pending_additions):
        batch = pending_additions[i:i + batch_size]

        print(f'🔄 [{processed}/{total}] Добавляю партию {len(batch)}, батч-размер {batch_size}...')
        (put_status, put_body_data, put_err), put_body = put_batch(batch)
        ok = put_err is None and put_status == 200

        if not ok:
            print('⚠️  Ошибка пакета, повторная попытка тем же пакетом...')
            time.sleep(2)
            (put_status, put_body_data, put_err), put_body = put_batch(batch)
            ok = put_err is None and put_status == 200

        if ok:
            active_mirrors = list(put_body["counter"]["mirrors"])
            for s in batch:
                existing_status[s] = ""
                added_count += 1
                processed += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [s, "✅ Добавлен"]}, ensure_ascii=False)}')
            i += len(batch)
            batch_size = DEFAULT_BATCH_SIZE
            continue

        error_detail = put_err if put_err else put_error_str(put_status, put_body_data)
        if batch_size > 10:
            print(f'❌ Ошибка пакета ({len(batch)}): {error_detail}. Уменьшаю пакет до 10...')
            batch_size = 10
            continue
        if batch_size > 1:
            print(f'❌ Ошибка группы ({len(batch)}): {error_detail}. Уменьшаю пакет до 1...')
            batch_size = 1
            continue

        print(f'❌ Ошибка добавления сайта: {error_detail}')
        error_count += 1
        processed += 1
        print(f'__TABLE_ROW__:{json.dumps({"cells": [batch[0], f"❌ {error_detail}"]}, ensure_ascii=False)}')
        i += 1
        batch_size = DEFAULT_BATCH_SIZE

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