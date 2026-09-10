import json
import os
import sys
import time
import requests

DEBUG = False


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
    data_file = os.path.join(arrays_dir, 'yandex_add_sites.json')
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


def normalize_host_url(url):
    url = url.strip()
    if '://' not in url:
        url = 'https://' + url
    return url.rstrip('/')


def normalize_host(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def api_request(method, url, headers, json_body=None, retries=3, timeout=10):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            log_api(method, url, resp.status_code)
            if resp.status_code in (200, 201, 204):
                try:
                    body = resp.json()
                except Exception:
                    body = None
                log_api(method, url, resp.status_code, body)
                return resp.status_code, body, None
            try:
                err_body = resp.json()
            except Exception:
                err_body = {"raw": resp.text[:500]}
            log_api(method, url, resp.status_code, err_body)
            return resp.status_code, err_body, None
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


def main():
    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить')
        return

    user_id = config.get('user_id')
    if not user_id:
        print('⚠️  Для запуска скрипта не хватает данных: user_id')
        print('ℹ️  Получите user_id на вкладке Яндекс → Ключи → Получить')
        return

    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        sites = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        sites = list(links_raw)
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
    log(f'user_id: {user_id}')
    log(f'Сайтов: {len(sites)}')
    log(f'Список: {sites}')

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Сайтов к добавлению: {len(sites)}')

    print(f'ℹ️  Получаю список сайтов из вебмастера...')
    status, hosts_data, err = api_request(
        'GET',
        f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts',
        headers
    )
    if err:
        print(f'⚠️  Ошибка получения списка сайтов: {err}')
        return
    if status != 200:
        error_msg = hosts_data.get('error_message', f'HTTP {status}') if isinstance(hosts_data, dict) else f'HTTP {status}'
        print(f'⚠️  Ошибка получения списка сайтов: {error_msg}')
        return

    all_hosts = hosts_data.get('hosts', []) if isinstance(hosts_data, dict) else []
    existing_hosts = {normalize_host(h.get('unicode_host_url', '')) for h in all_hosts}
    log(f'Получено хостов: {len(all_hosts)}')

    added_count = 0
    already_count = 0
    error_count = 0
    limit_reached = False

    for i, site in enumerate(sites, 1):
        print(f'🔄 [{i}/{len(sites)}] {site}')

        if normalize_host(site) in existing_hosts:
            already_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "ℹ️ Уже существует"]}, ensure_ascii=False)}')
            time.sleep(0.3)
            continue

        host_url = normalize_host_url(site)
        status, body, err = api_request(
            'POST',
            f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts',
            headers,
            json_body={"host_url": host_url}
        )

        if err:
            print(f'   ❌ Ошибка соединения: {err}')
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {err}"]}, ensure_ascii=False)}')
        elif status == 201:
            added_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "✅ Добавлен"]}, ensure_ascii=False)}')
        elif status == 409:
            error_code = body.get('error_code', '') if isinstance(body, dict) else ''
            if error_code == 'HOST_ALREADY_ADDED':
                print(f'   ℹ️  Уже существует')
                already_count += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "ℹ️ Уже существует"]}, ensure_ascii=False)}')
            else:
                print(f'   ❌ {error_code}')
                error_count += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {error_code}"]}, ensure_ascii=False)}')
        elif status == 403:
            error_code = body.get('error_code', '') if isinstance(body, dict) else ''
            if error_code == 'HOSTS_LIMIT_EXCEEDED':
                limit_msg = f'⚠️ Достигнут лимит сайтов ({body.get("limit", "?")})'
                print(f'   {limit_msg}')
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"⚠️ {limit_msg}"]}, ensure_ascii=False)}')
                print(f'⚠️  {limit_msg} — further sites skipped')
                limit_reached = True
                break
            elif error_code == 'INVALID_USER_ID':
                print(f'   ❌ Неверный user_id')
                error_count += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "❌ INVALID_USER_ID"]}, ensure_ascii=False)}')
            else:
                error_msg = body.get('error_message', error_code) if isinstance(body, dict) else error_code
                print(f'   ❌ {error_msg}')
                error_count += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {error_code}"]}, ensure_ascii=False)}')
        else:
            error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
            print(f'   ❌ {error_code}')
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {error_code}"]}, ensure_ascii=False)}')

    remaining = len(sites) - (added_count + already_count + error_count)
    print()
    summary = {
        "Всего в списке": len(sites),
        "Добавлено": added_count,
        "Уже существовало": already_count,
        "Ошибок": error_count
    }
    if limit_reached:
        summary["Остаток (пропущено)"] = remaining
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()
