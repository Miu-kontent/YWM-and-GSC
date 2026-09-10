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
    data_file = os.path.join(arrays_dir, 'yandex_add_sitemap.json')
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


def api_request(method, url, headers, json_body=None, retries=3, timeout=10):
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

    raw_sitemap = config.get('sitemap_path', '')
    if isinstance(raw_sitemap, list):
        sitemap_path = raw_sitemap[0].strip() if raw_sitemap else ''
    elif raw_sitemap:
        sitemap_path = raw_sitemap.strip()
    else:
        sitemap_path = ''

    if not sitemap_path:
        print('⚠️  Для запуска скрипта не хватает данных: sitemap_path')
        print('ℹ️  Укажите путь сайтмапа на вкладке Яндекс → Ключи → Параметры')
        return

    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        sites = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        sites = [str(l).strip() for l in links_raw if str(l).strip()]
    else:
        sites = []

    if not sites:
        print('❌ Нет сайтов для обработки!')
        return

    headers = {
        'Authorization': f'OAuth {token}',
        'Content-Type': 'application/json'
    }

    log(f'token: {token[:20]}...')
    log(f'user_id: {user_id}')
    log(f'sitemap_path: {sitemap_path}')
    log(f'Сайтов: {len(sites)}')
    log(f'Список: {sites}')

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Путь сайтмапа: {sitemap_path}')
    print(f'ℹ️  Сайтов к обработке: {len(sites)}')

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
    hosts_index = {}
    for h in all_hosts:
        host_id = h.get('host_id', '')
        for url_key in ('unicode_host_url', 'ascii_host_url'):
            hostname = normalize_host(h.get(url_key, ''))
            if hostname and hostname not in hosts_index:
                hosts_index[hostname] = host_id
    log(f'Получено хостов: {len(all_hosts)}')

    added_count = 0
    already_count = 0
    error_count = 0

    for i, site in enumerate(sites, 1):
        hostname = normalize_host(site)
        sitemap_url = f'https://{hostname}{sitemap_path}'

        print(f'🔄 [{i}/{len(sites)}] {site}')
        print(f'   {sitemap_url}')

        host_id = hosts_index.get(hostname)
        if not host_id:
            host_id = f'https:{hostname}:443'
            log(f'  Не найден host_id, формирую: {host_id}')

        status, body, err = api_request(
            'POST',
            f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/user-added-sitemaps',
            headers,
            json_body={"url": sitemap_url}
        )

        if err:
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, sitemap_url, f"❌ {err}"]}, ensure_ascii=False)}')
        elif status == 201:
            added_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, sitemap_url, "✅ Добавлен"]}, ensure_ascii=False)}')
        elif status == 409:
            error_code = body.get('error_code', '') if isinstance(body, dict) else ''
            if error_code == 'SITEMAP_ALREADY_ADDED':
                already_count += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, sitemap_url, "ℹ️ Уже добавлен"]}, ensure_ascii=False)}')
            else:
                error_count += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site, sitemap_url, f"❌ {error_code}"]}, ensure_ascii=False)}')
        elif status == 404:
            error_code = body.get('error_code', f'HTTP 404') if isinstance(body, dict) else f'HTTP 404'
            msg = 'Сайт не подтверждён' if error_code == 'HOST_NOT_VERIFIED' else error_code
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, sitemap_url, f"❌ {msg}"]}, ensure_ascii=False)}')
        else:
            error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, sitemap_url, f"❌ {error_code}"]}, ensure_ascii=False)}')

    print()
    summary = {
        "Всего": len(sites),
        "Добавлено": added_count,
        "Уже было": already_count,
        "Ошибок": error_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()