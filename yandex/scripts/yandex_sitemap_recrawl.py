import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

BASE_URL = 'https://api.webmaster.yandex.net'
DEBUG = False


def log(msg):
    if DEBUG:
        print(f'[DEBUG] {msg}')


def log_api(method, url, status, body=None):
    if DEBUG:
        log(f'{method} {url} -> {status}')
        if body is not None:
            log(f'  body: {json.dumps(body, ensure_ascii=False)[:500]}')


def load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def load_script_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_file = os.path.join(script_dir, '..', 'arrays', 'yandex_sitemap_recrawl.json')
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def normalize_host(url):
    if not url:
        return ''
    url = str(url).strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def fmt_date(value):
    if not value:
        return '-'
    s = str(value)
    parts = s[:10].split('-')
    if len(parts) == 3 and len(parts[0]) == 4:
        return f'{parts[2]}.{parts[1]}.{parts[0]}'
    return s


def api_request(method, url, headers, params=None, json_body=None, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout)
            log_api(method, resp.url, resp.status_code)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            log_api(method, resp.url, resp.status_code, body)
            return resp.status_code, body, None
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return None, None, f'Соединение не установлено после {retries} попыток'
            time.sleep(1)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, None, f'Превышен таймаут ({timeout}с) после {retries} попыток'
            time.sleep(1)
        except Exception as e:
            return None, None, str(e)
    return None, None, "Unknown error"


def is_mirror(h):
    mm = h.get('main_mirror') or {}
    return bool(mm.get('host_id') or mm.get('unicode_host_url'))


def get_recrawl_limits(user_id, host_id, headers):
    url = f'{BASE_URL}/v4.1/user/{user_id}/hosts/{host_id}/sitemaps/recrawl'
    status, body, err = api_request('GET', url, headers)
    if err:
        return None, None, None, err
    if status != 200:
        code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
        return None, None, None, code
    info = body.get('host_sitemaps_recrawl_limit_info') or {}
    return (
        info.get('monthly_limit_requests'),
        info.get('requests_count'),
        info.get('nearest_allowed_day'),
        None
    )


def match_sitemap(sm_url, hostname, path):
    try:
        parsed = urlparse(sm_url)
    except Exception:
        return False
    if (parsed.hostname or '').lower() != hostname:
        return False
    return (parsed.path or '') == path


def find_sitemap_id(user_id, host_id, headers, hostname, path):
    from_id = None
    for _ in range(20):
        params = {'limit': 100}
        if from_id:
            params['from'] = from_id
        status, body, err = api_request(
            'GET',
            f'{BASE_URL}/v4/user/{user_id}/hosts/{host_id}/sitemaps',
            headers,
            params=params
        )
        if err:
            return None, err
        if status != 200:
            code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
            if code == 'HOST_NOT_VERIFIED':
                return None, 'сайт не подтверждён'
            return None, code
        sitemaps = body.get('sitemaps', []) if isinstance(body, dict) else []
        if not sitemaps:
            return None, None
        for sm in sitemaps:
            if match_sitemap(sm.get('sitemap_url', ''), hostname, path):
                sid = sm.get('sitemap_id')
                if sid:
                    return sid, None
        if len(sitemaps) < 100:
            return None, None
        from_id = sitemaps[-1].get('sitemap_id')
        if not from_id:
            return None, None
    return None, None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    user_id = config.get('user_id')
    sitemap_path = (config.get('sitemap_path') or '').strip()
    if sitemap_path and not sitemap_path.startswith('/'):
        sitemap_path = '/' + sitemap_path
    show_limits = bool(script_data.get('show_limits', False))

    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить')
        return
    if not user_id:
        print('⚠️  Для запуска скрипта не хватает данных: user_id')
        print('ℹ️  Получите user_id на вкладке Яндекс → Ключи → Получить')
        return
    if not sitemap_path:
        print('⚠️  Для запуска скрипта не хватает данных: sitemap_path')
        print('ℹ️  Заполните поле «Путь сайтмапа» на вкладке Яндекс → Ключи')
        return

    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        sites = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        sites = [str(l).strip() for l in links_raw if str(l).strip()]
    else:
        sites = []

    headers = {
        'Authorization': f'OAuth {token}',
        'Content-Type': 'application/json'
    }

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Путь сайтмапа: {sitemap_path}')
    print('ℹ️  Вывод лимитов переобхода: включён' if show_limits else 'ℹ️  Вывод лимитов переобхода: выключен')

    print('ℹ️  Получаю список сайтов из Вебмастера...')
    status, hosts_data, err = api_request('GET', f'{BASE_URL}/v4/user/{user_id}/hosts', headers)
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
        if is_mirror(h):
            continue
        hid = h.get('host_id', '')
        if not hid:
            continue
        for url_key in ('unicode_host_url', 'ascii_host_url'):
            hostname = normalize_host(h.get(url_key, ''))
            if hostname and hostname not in hosts_index:
                hosts_index[hostname] = hid

    if not sites:
        for h in all_hosts:
            if is_mirror(h):
                continue
            hostname = normalize_host(h.get('ascii_host_url', '') or h.get('unicode_host_url', ''))
            if hostname:
                sites.append(hostname)
        print(f'ℹ️  Режим: все сайты из Вебмастера ({len(sites)})')
    else:
        sites = [normalize_host(s) for s in sites if s]
        print(f'ℹ️  Сайтов из списка: {len(sites)}')

    if not sites:
        print('❌ Нет сайтов для обработки!')
        return

    total = len(sites)
    sent_count = 0
    previously_count = 0
    fail_count = 0

    for i, site in enumerate(sites, 1):
        hostname = normalize_host(site)
        target_url = f'https://{hostname}{sitemap_path}'
        print(f'🔄 [{i}/{total}] {site}')

        host_id = hosts_index.get(hostname, '')
        if not host_id:
            host_id = f'https:{hostname}:443'

        remaining = None
        nearest = None
        if show_limits:
            lim_total, lim_used, lim_nearest, lim_err = get_recrawl_limits(user_id, host_id, headers)
            if lim_err:
                print(f'   ⚠️  Не удалось получить лимиты: {lim_err}')
            elif lim_total is not None and lim_used is not None:
                remaining = max(lim_total - lim_used, 0)
                nearest = lim_nearest
                if remaining < 1:
                    fail_count += 1
                    cells = [site, str(remaining), fmt_date(nearest), target_url, f'❌ Лимит исчерпан (след. {fmt_date(nearest)})']
                    print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
                    continue

        sid, sm_err = find_sitemap_id(user_id, host_id, headers, hostname, sitemap_path)
        if sm_err:
            fail_count += 1
            cells = [site, target_url, f'❌ {sm_err}']
        elif not sid:
            fail_count += 1
            cells = [site, target_url, '❌ Sitemap не найден']
        else:
            resp_status, resp_body, resp_err = api_request(
                'POST',
                f'{BASE_URL}/v4.1/user/{user_id}/hosts/{host_id}/sitemaps/{sid}/recrawl',
                headers
            )
            if resp_err:
                fail_count += 1
                cells = [site, target_url, f'❌ {resp_err}']
            elif resp_status in (200, 202):
                sent_count += 1
                cells = [site, target_url, '✅ Отправлен']
            elif resp_status == 409:
                previously_count += 1
                cells = [site, target_url, '⭐ Отправлен ранее']
            elif resp_status == 429:
                fail_count += 1
                cells = [site, target_url, '❌ Лимиты исчерпаны']
            elif resp_status == 404:
                code = resp_body.get('error_code', 'HTTP 404') if isinstance(resp_body, dict) else 'HTTP 404'
                if code == 'SITEMAP_NOT_FOUND':
                    cells = [site, target_url, '❌ Sitemap не найден']
                elif code == 'HOST_NOT_VERIFIED':
                    cells = [site, target_url, '❌ Сайт не подтверждён']
                else:
                    cells = [site, target_url, f'❌ {code}']
                fail_count += 1
            else:
                code = resp_body.get('error_code', f'HTTP {resp_status}') if isinstance(resp_body, dict) else f'HTTP {resp_status}'
                fail_count += 1
                cells = [site, target_url, f'❌ {code}']

        if show_limits:
            cells = [
                site,
                str(remaining) if remaining is not None else '-',
                fmt_date(nearest) if nearest else '-',
                target_url,
                cells[-1]
            ]
        print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')

    print()
    summary = {
        "Сайтов": total,
        "Путь сайтмапа": sitemap_path,
        "Отправлено": sent_count,
        "Отправлено ранее": previously_count,
        "Ошибок": fail_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()