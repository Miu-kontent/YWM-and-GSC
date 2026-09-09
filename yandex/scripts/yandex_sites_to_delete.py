import json
import os
import sys
import time
import requests


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


def extract_site_url(url):
    if not url:
        return ''
    if '://' in url:
        url = url.split('://', 1)[1]
    return url.rstrip('/')


def get_host_id_from_url(hosts, target_url):
    target = extract_site_url(target_url).lower()
    for h in hosts:
        h_url = extract_site_url(h.get('unicode_host_url', '')).lower()
        if h_url == target:
            return h.get('host_id')
    return None


def api_get(url, headers, params=None, retries=5, timeout=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return None, f"Соединение не установлено после {retries} попыток"
            time.sleep(1)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, f"Превышен таймаут ({timeout}с) после {retries} попыток"
            time.sleep(1)
        except Exception as e:
            return None, str(e)
    return None, "Unknown error"


def api_delete(url, headers, retries=3, timeout=10):
    for attempt in range(retries):
        try:
            resp = requests.delete(url, headers=headers, timeout=timeout)
            if resp.status_code in (200, 204):
                return True, None
            if resp.status_code == 404:
                return False, "HOST_NOT_FOUND"
            if resp.status_code == 403:
                return False, "INVALID_USER_ID"
            try:
                err = resp.json()
                return False, err.get('error_code', f"HTTP {resp.status_code}")
            except Exception:
                return False, f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return False, f"Соединение не установлено после {retries} попыток"
            time.sleep(2)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return False, f"Превышен таймаут ({timeout}с) после {retries} попыток"
            time.sleep(2)
        except Exception as e:
            return False, str(e)
    return False, "Unknown error"


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
        sites_to_delete = links_raw
    else:
        sites_to_delete = []

    if not sites_to_delete:
        print('❌ Нет сайтов для удаления!')
        return

    headers = {'Authorization': f'OAuth {token}'}

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Сайтов к удалению: {len(sites_to_delete)}')
    print()

    hosts_data, err = api_get(f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts', headers)
    if err:
        print(f'⚠️  Ошибка получения списка сайтов: {err}')
        return

    all_hosts = hosts_data.get('hosts', [])

    deleted_count = 0
    not_found_count = 0
    error_count = 0
    errors = []

    for i, site in enumerate(sites_to_delete, 1):
        print(f'🔄 [{i}/{len(sites_to_delete)}] {site}')

        host_id = get_host_id_from_url(all_hosts, site)
        if not host_id:
            print(f'   ❌ Не найден в вебмастере')
            not_found_count += 1
            errors.append({'site': site, 'error': 'HOST_NOT_FOUND'})
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "❌ Не найден"]}, ensure_ascii=False)}')
            continue

        delete_url = f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}'
        success, err = api_delete(delete_url, headers)

        if success:
            print(f'   ✅ Удалён (host_id: {host_id})')
            deleted_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "✅ Удалён"]}, ensure_ascii=False)}')
        else:
            print(f'   ❌ Ошибка: {err}')
            error_count += 1
            errors.append({'site': site, 'error': err})
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ {err}"]}, ensure_ascii=False)}')

        time.sleep(0.5)

    print()
    print(f'__SUMMARY__:{json.dumps({"Всего": len(sites_to_delete), "Удалено": deleted_count, "Не найдено": not_found_count, "Ошибок": error_count}, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()