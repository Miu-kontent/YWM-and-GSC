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
    data_file = os.path.join(arrays_dir, 'yandex_sites_to_delete.json')
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


def normalize_url(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ''
    port = parsed.port
    scheme = parsed.scheme or 'http'
    if port and ((scheme == 'http' and port != 80) or (scheme == 'https' and port != 443)):
        return f'{scheme}:{host}:{port}'
    return f'{scheme}:{host}:{"443" if scheme == "https" else "80"}'


def normalize_unicode_url(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    return host


def get_host_id_from_url(hosts, target_url):
    target = normalize_unicode_url(target_url)
    log(f'Ищу хост для "{target_url}" (normalized: "{target}")')
    log(f'Доступные хосты ({len(hosts)}):')
    for h in hosts:
        h_url = h.get('unicode_host_url', '')
        h_id = h.get('host_id', '')
        log(f'  host_id={h_id}  unicode_url={h_url}')
        if normalize_unicode_url(h_url) == target:
            log(f'  → СОВПАДЕНИЕ: host_id={h_id}')
            return h_id
    log(f'  → СОВПАДЕНИЕ НЕ НАЙДЕНО для "{target}"')
    return None


def api_request(method, url, headers, params=None, retries=5, timeout=5):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, params=params, timeout=timeout)
            log_api(method, url, resp.status_code)
            if resp.status_code in (200, 204):
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
        sites_to_delete = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        sites_to_delete = list(links_raw)
    else:
        sites_to_delete = []

    if not sites_to_delete:
        print('❌ Нет сайтов для удаления!')
        return

    headers = {'Authorization': f'OAuth {token}'}

    log(f'token: {token[:20]}...')
    log(f'user_id: {user_id}')
    log(f'Сайтов к удалению: {len(sites_to_delete)}')
    log(f'Список: {sites_to_delete}')

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Сайтов к удалению: {len(sites_to_delete)}')

    log('Получаю список всех сайтов из вебмастера...')
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
        if hosts_data:
            print(f'   Ответ API: {json.dumps(hosts_data, ensure_ascii=False)[:300]}')
        return

    all_hosts = hosts_data.get('hosts', []) if isinstance(hosts_data, dict) else []
    log(f'Получено хостов: {len(all_hosts)}')

    if not all_hosts:
        print('⚠️  Список сайтов пуст — ни одного сайта в вебмастере не найдено')
        print(f'   Ответ API: {json.dumps(hosts_data, ensure_ascii=False)[:300]}')
        return

    deleted_count = 0
    not_found_count = 0
    error_count = 0

    for i, site in enumerate(sites_to_delete, 1):
        print(f'🔄 [{i}/{len(sites_to_delete)}] {site}')

        host_id = get_host_id_from_url(all_hosts, site)
        if not host_id:
            print(f'   ❌ Не найден в вебмастере')
            not_found_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "❌ Не найден"]}, ensure_ascii=False)}')
            continue

        delete_url = f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}'
        log(f'Удаляю: DELETE {delete_url}')
        status, body, err = api_request('DELETE', delete_url, headers)

        if err:
            print(f'   ❌ Ошибка соединения: {err}')
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {err}"]}, ensure_ascii=False)}')
        elif status in (200, 204):
            deleted_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "✅ Удалён"]}, ensure_ascii=False)}')
        else:
            error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
            error_msg = body.get('error_message', '') if isinstance(body, dict) else ''
            detail = f'{error_code}: {error_msg}' if error_msg else error_code
            print(f'   ❌ Ошибка: {detail}')
            if DEBUG and body:
                print(f'   [DEBUG] Ответ: {json.dumps(body, ensure_ascii=False)[:300]}')
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {error_code}"]}, ensure_ascii=False)}')

        # time.sleep(0.2)

    print()
    print(f'__SUMMARY__:{json.dumps({"Всего": len(sites_to_delete), "Удалено": deleted_count, "Не найдено": not_found_count, "Ошибок": error_count}, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()