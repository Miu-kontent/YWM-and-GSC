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
    data_file = os.path.join(arrays_dir, 'yandex_verify.json')
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


def get_host_id_from_url(hosts, target_url):
    target = normalize_host(target_url)
    log(f'Ищу хост для "{target_url}" (normalized: "{target}")')
    for h in hosts:
        h_url = h.get('unicode_host_url', '')
        if normalize_host(h_url) == target:
            log(f'  → Найден: host_id={h.get("host_id")}, verified={h.get("verified")}')
            return h.get('host_id'), h.get('verified', False)
    log(f'  → Не найден в hosts')
    return None, None


def api_request(method, url, headers, params=None, retries=3, timeout=10):
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


def get_verification_code(headers, user_id, host_id):
    url = f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/verification'
    log(f'GET verification code: {url}')
    status, body, err = api_request('GET', url, headers)
    if err:
        log(f'  Ошибка получения кода: {err}')
        return None, err
    if status != 200:
        error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
        log(f'  Ошибка API: {error_code}')
        return None, error_code
    uin = body.get('verification_uin') if isinstance(body, dict) else None
    log(f'  verification_uin: {uin}')
    return uin, None


def try_verify(headers, user_id, host_id, method):
    url = f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/verification'
    params = {'verification_type': method}
    log(f'POST verification ({method}): {url}')
    status, body, err = api_request('POST', url, headers, params=params)
    if err:
        log(f'  Ошибка соединения: {err}')
        return False, err
    if status in (200, 204):
        state = body.get('verification_state', '') if isinstance(body, dict) else ''
        log(f'  Успех: state={state}')
        return True, state
    error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
    log(f'  Ошибка: {error_code}')
    return False, error_code


def get_verification_status(headers, user_id, host_id):
    url = f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/verification'
    log(f'GET verification status: {url}')
    status, body, err = api_request('GET', url, headers)
    if err:
        log(f'  Ошибка получения статуса: {err}')
        return None, err
    if status != 200:
        error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
        log(f'  Ошибка API: {error_code}')
        return None, error_code
    state = body.get('verification_state', '') if isinstance(body, dict) else ''
    log(f'  verification_state: {state}')
    return state, body if isinstance(body, dict) else None


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
        print('❌ Нет сайтов для подтверждения!')
        return

    headers = {'Authorization': f'OAuth {token}'}

    log(f'token: {token[:20]}...')
    log(f'user_id: {user_id}')
    log(f'Сайтов: {len(sites)}')
    log(f'Список: {sites}')

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Сайтов к подтверждению: {len(sites)}')

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
    log(f'Получено хостов: {len(all_hosts)}')

    already_verified = 0
    newly_verified = 0
    error_count = 0
    meta_count = 0
    html_count = 0
    dns_count = 0
    newly_verified_sites = {}  # site -> {host_id, method}

    for i, site in enumerate(sites, 1):
        print(f'🔄 [{i}/{len(sites)}] {site}')

        host_id, verified = get_host_id_from_url(all_hosts, site)

        if host_id and verified:
            already_verified += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "✅ Уже подтверждён"]}, ensure_ascii=False)}')
            continue

        if not host_id:
            log(f'  Сайт не найден в hosts, пробуем подтверждение по URL...')
            target = normalize_host(site)
            host_id = f'https:{target}:443'
            log(f'  Сформирован host_id: {host_id}')

        uin, err = get_verification_code(headers, user_id, host_id)
        if err:
            print(f'   ❌ Не удалось получить код подтверждения: {err}')
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"❌ Ошибка: {err}"]}, ensure_ascii=False)}')
            continue

        success = False
        used_method = None

        for method in ['META_TAG', 'HTML_FILE', 'DNS']:
            log(f'  Пробуем {method}...')
            ok, result = try_verify(headers, user_id, host_id, method)
            if ok:
                success = True
                used_method = method
                break
            if result == 'VERIFICATION_ALREADY_IN_PROGRESS':
                success = True
                used_method = f'{method} (уже в процессе)'
                break
            log(f'  {method} не сработал: {result}')
            time.sleep(0.3)

        if success:
            newly_verified += 1
            newly_verified_sites[site] = {"host_id": host_id, "method": used_method}
            if 'META_TAG' in used_method:
                meta_count += 1
            elif 'HTML_FILE' in used_method:
                html_count += 1
            elif 'DNS' in used_method:
                dns_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, f"✅ {used_method}"]}, ensure_ascii=False)}')
        else:
            print(f'   ❌ Ни один метод не сработал')
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "❌ Все методы не сработали"]}, ensure_ascii=False)}')

    if newly_verified_sites:
        print(f'ℹ️  Жду 10 сек перед повторной проверкой статуса...')
        time.sleep(10)
        print(f'ℹ️  Перепроверяю статус подтверждения ({len(newly_verified_sites)} сайтов)...')
        status, hosts_data, err = api_request(
            'GET',
            f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts',
            headers
        )
        fresh_hosts = None
        if err:
            log(f'  Ошибка повторного получения списка сайтов: {err}')
        elif status == 200 and isinstance(hosts_data, dict):
            fresh_hosts = hosts_data.get('hosts', [])

        failed_sites = []
        for site, info in newly_verified_sites.items():
            if fresh_hosts is not None and fresh_hosts:
                fresh_host_id, fresh_verified = get_host_id_from_url(fresh_hosts, site)
            else:
                fresh_host_id, fresh_verified = info['host_id'], None

            if fresh_verified:
                log(f'  {site} → confirmed (verified=True)')
                continue

            state, body = get_verification_status(headers, user_id, fresh_host_id or info['host_id'])
            if state is None:
                continue

            if state in ('VERIFICATION_FAILED', 'INTERNAL_ERROR'):
                failed_sites.append((site, state))
                log(f'  {site} → FAILED: {state}')

        if failed_sites:
            print(f'⚠️  Обнаружены сайты, не подтверждённые повторной проверкой: {len(failed_sites)}')
            for site, details in failed_sites:
                info = newly_verified_sites[site]
                method = info['method']
                if 'META_TAG' in method:
                    meta_count -= 1
                elif 'HTML_FILE' in method:
                    html_count -= 1
                elif 'DNS' in method:
                    dns_count -= 1
                newly_verified -= 1
                error_count += 1
                print(f'__REPLACE_TABLE_ROW__:{json.dumps({"site": site, "cells": [site, f"❌ {details}"]}, ensure_ascii=False)}')

    print()
    summary = {
        "Всего": len(sites),
        "Уже подтверждены": already_verified,
        "Подтверждено": newly_verified,
        "  через META_TAG": meta_count,
        "  через HTML_FILE": html_count,
        "  через DNS": dns_count,
        "Ошибок": error_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()
