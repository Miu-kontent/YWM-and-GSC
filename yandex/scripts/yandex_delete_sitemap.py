import json
import os
import sys
import time
import requests

DEBUG = False

BASE_URL = 'https://api.webmaster.yandex.net'


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
    array_path = os.path.join(script_dir, '..', 'arrays', 'yandex_delete_sitemap.json')
    if os.path.exists(array_path):
        with open(array_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def normalize_host(url):
    if not url:
        return ''
    url = str(url).strip()
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
                return None, None, f"Connection error after {retries} attempts"
            time.sleep(1)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, None, f"Timeout ({timeout}s) after {retries} attempts"
            time.sleep(1)
        except Exception as e:
            return None, None, str(e)
    return None, None, "Unknown error"


def main():
    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    if not token:
        print('! [WARN] Missing data: oauth_token')
        print('i  Get token on Yandex tab -> Keys -> Get')
        return

    user_id = config.get('user_id')
    if not user_id:
        print('! [WARN] Missing data: user_id')
        print('i  Get user_id on Yandex tab -> Keys -> Get')
        return

    raw_path = script_data.get('sitemap_path', '')
    if isinstance(raw_path, list):
        sitemap_path = raw_path[0].strip() if raw_path else ''
    elif raw_path:
        sitemap_path = raw_path.strip()
    else:
        sitemap_path = ''

    if not sitemap_path:
        print('! [WARN] Missing data: sitemap_path')
        return

    if not sitemap_path.startswith('/'):
        sitemap_path = '/' + sitemap_path

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

    print(f'i  user_id: {user_id}')
    print(f'i  Sitemap path: {sitemap_path}')

    all_hosts = []
    if sites:
        print(f'i  Sites from list: {len(sites)}')
    else:
        print('i  Loading all sites from Webmaster...')
        status, hosts_data, err = api_request('GET', f'{BASE_URL}/user/{user_id}/hosts', headers)
        if err:
            print(f'! [ERROR] Failed to load hosts: {err}')
            return
        if status != 200:
            error_msg = hosts_data.get('error_message', f'HTTP {status}') if isinstance(hosts_data, dict) else f'HTTP {status}'
            print(f'! [ERROR] Failed to load hosts: {error_msg}')
            return
        all_hosts = hosts_data.get('hosts', []) if isinstance(hosts_data, dict) else []
        is_mirror = lambda h: bool(h.get('host_id') or h.get('unicode_host_url'))
        all_hosts = [h for h in all_hosts if is_mirror(h)]
        sites = []
        for h in all_hosts:
            h_url = h.get('ascii_host_url', '') or h.get('unicode_host_url', '')
            hostname = normalize_host(h_url)
            if hostname:
                sites.append(hostname)
        print(f'i  All sites (no mirrors): {len(sites)}')

    if not sites:
        print('! [WARN] No sites to process')
        return

    hosts_index = {}
    for h in all_hosts:
        hid = h.get('host_id', '')
        for url_key in ('unicode_host_url', 'ascii_host_url'):
            hostname = normalize_host(h.get(url_key, ''))
            if hostname and hostname not in hosts_index:
                hosts_index[hostname] = hid

    removed_count = 0
    not_found_count = 0
    error_count = 0

    for i, site in enumerate(sites, 1):
        hostname = site if '.' in site else normalize_host(site)
        if not hostname:
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "-", "! Invalid site"]}, ensure_ascii=False)}')
            continue

        target_url = f'https://{hostname}{sitemap_path}'
        print(f'[{i}/{len(sites)}] {hostname}')

        host_id = hosts_index.get(hostname)
        if not host_id:
            host_id = f'https:{hostname}:443'
            log(f'  host_id not found, generated: {host_id}')

        status, body, err = api_request(
            'GET',
            f'{BASE_URL}/user/{user_id}/hosts/{host_id}/user-added-sitemaps',
            headers
        )

        if err:
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, target_url, f"! {err}"]}, ensure_ascii=False)}')
            continue

        if status != 200:
            error_code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
            error_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, target_url, f"! {error_code}"]}, ensure_ascii=False)}')
            continue

        sitemaps_list = body.get('sitemaps', []) if isinstance(body, dict) else []
        matches = [s for s in sitemaps_list if s.get('sitemap_url', '') == target_url]

        if not matches:
            not_found_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, target_url, "Not found"]}, ensure_ascii=False)}')
            continue

        site_removed = 0
        site_errors = 0
        for s in matches:
            sid = s.get('sitemap_id', '')
            if not sid:
                site_errors += 1
                continue
            del_status, del_body, del_err = api_request(
                'DELETE',
                f'{BASE_URL}/user/{user_id}/hosts/{host_id}/user-added-sitemaps/{sid}',
                headers
            )
            if del_err:
                site_errors += 1
                log(f'  DELETE {sid} error: {del_err}')
            elif del_status == 204:
                site_removed += 1
                log(f'  DELETE {sid} -> 204 OK')
            else:
                site_errors += 1
                ec = del_body.get('error_code', f'HTTP {del_status}') if isinstance(del_body, dict) else f'HTTP {del_status}'
                log(f'  DELETE {sid} -> {del_status} {ec}')

        if site_errors:
            error_count += 1
            status_text = f'! Partial: {site_removed} deleted, {site_errors} errors'
        else:
            removed_count += 1
            status_text = 'Deleted' if site_removed == 1 else f'Deleted ({site_removed})'

        print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, target_url, status_text]}, ensure_ascii=False)}')

    print()
    summary = {
        "Сайтов": len(sites),
        "Путь сайтмапа": sitemap_path,
        "Удалено": removed_count,
        "Не найдено": not_found_count,
        "Ошибок": error_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()
