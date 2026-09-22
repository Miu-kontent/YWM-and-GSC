"""
yandex_delete_sitemaps_except.py — удаление всех sitemap, КРОМЕ указанных в списке "keep".

Для каждого сайта из списка links (обязательно) находит все сайтмапы через
GET /v4/user/{uid}/hosts/{hid}/sitemaps (обработанные) и
GET /v4/user/{uid}/hosts/{hid}/user-added-sitemaps (добавленные пользователем,
ещё не обработанные, но уже удаляемые).

Особенности Яндекса:
    sitemap может иметь источник (source): ROBOTS_TXT и/или WEBMASTER.
    Удалить можно только сайтмапы с source WEBMASTER и добавленные через
    user-added-sitemaps; сайтмапы из robots.txt удалить нельзя — они просто
    помечаются как «сайтмапы из робота».

Вход (yandex/arrays/yandex_delete_sitemaps_except.json):
    links — сайты (по одному на строке), ОБЯЗАТЕЛЬНО.
    keep_sitemaps — список путей sitemap, которые нужно ОСТАВИТЬ (не удалять).

Формат таблицы:
    Сайт | Сайтмапы из робота | Сайтмапы пользователя | Статусы сайтмапов пользователя
        (сайтмапы пользователя и их статусы — списками в одной ячейке;
        статусы параллельны сайтмапам: удалён/оставлен).
Пути для сохранения (keep_sitemaps) выводятся в краткой сводке.
Краткая сводка: Сайтов | Сайтмапы для сохранения | Оставлено | Удалено |
    Файлов из робота | Не найдено | Ошибок.
"""
import json
import os
import sys
import time

import requests

from yandex_client import load_config

from urllib.parse import urlparse

BASE_URL = 'https://api.webmaster.yandex.net/v4'
RETRY_CODES = (429, 500, 502, 503, 504)
RETRY_SLEEP = 0.5


def load_script_data():
    array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'yandex_delete_sitemaps_except.json')
    if not os.path.exists(array_path):
        return {}
    try:
        with open(array_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def parse_links(value):
    if isinstance(value, str):
        return [l.strip() for l in value.strip().split('\n') if l.strip()]
    if isinstance(value, list):
        return [str(l).strip() for l in value if str(l).strip()]
    return []


def normalize_keep_paths(paths):
    """Приводим пути к нормальному виду: начинаются с /, без двойных слешей."""
    if isinstance(paths, str):
        paths = [p for p in (item.strip() for item in paths.strip().split('\n')) if p]
    out = []
    for p in paths or []:
        p = str(p).strip()
        if not p:
            continue
        if '://' in p:
            try:
                p = urlparse(p).path or '/'
            except Exception:
                p = '/'
        if not p.startswith('/'):
            p = '/' + p
        while '//' in p:
            p = p.replace('//', '/')
        out.append(p)
    return out


def normalize_host(url):
    if not url:
        return ''
    url = str(url).strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def sitemap_path_of(full_url):
    try:
        parsed = urlparse(str(full_url))
    except Exception:
        return None
    return parsed.path or '/'


def sources_of(sm):
    """Источники сайтмапа: строка или список ('ROBOTS_TXT', 'WEBMASTER')."""
    raw = sm.get('source') or sm.get('sources')
    if isinstance(raw, list):
        return [str(s).upper() for s in raw]
    return [s.strip().upper() for s in str(raw or '').split(',') if s.strip()]


def is_webmaster_source(sm):
    return any('WEBMASTER' in s for s in sources_of(sm))


def is_robots_source(sm):
    return any('ROBOTS_TXT' in s for s in sources_of(sm))


def api_request(method, url, headers, params=None, json_body=None, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=timeout)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            if resp.status_code in RETRY_CODES and attempt < retries - 1:
                time.sleep(RETRY_SLEEP)
                continue
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


def list_sitemaps(user_id, host_id, headers):
    """Все сайтмапы хоста через /sitemaps (с пагинацией). Возвращает (sitemaps, err)."""
    sitemaps = []
    from_id = None
    for _ in range(50):
        params = {'limit': 100}
        if from_id:
            params['from'] = from_id
        status, body, err = api_request('GET', f'{BASE_URL}/user/{user_id}/hosts/{host_id}/sitemaps', headers, params=params)
        if err:
            return None, err
        if status != 200:
            code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
            return None, code
        items = body.get('sitemaps', []) if isinstance(body, dict) else []
        sitemaps.extend(items)
        if len(items) < 100:
            return sitemaps, None
        from_id = items[-1].get('sitemap_id')
        if not from_id:
            return sitemaps, None
    return sitemaps, None


def list_user_sitemaps(user_id, host_id, headers):
    """Сайтмапы, добавленные пользователем, но ещё не обработанные
    GET /user/{uid}/hosts/{hid}/user-added-sitemaps (их тоже можно удалять).
    Возвращает (sitemaps, err)."""
    status, body, err = api_request(
        'GET',
        f'{BASE_URL}/user/{user_id}/hosts/{host_id}/user-added-sitemaps',
        headers,
        params={'limit': 100}
    )
    if err:
        return None, err
    if status != 200:
        code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
        return None, code
    items = body.get('sitemaps', []) if isinstance(body, dict) else []
    return items, None


def delete_sitemap(user_id, host_id, headers, sitemap_id):
    """Удаляет сайтмап. Возвращает ('ok'|'not_found'|'err', err_text)."""
    status, body, err = api_request(
        'DELETE',
        f'{BASE_URL}/user/{user_id}/hosts/{host_id}/user-added-sitemaps/{sitemap_id}',
        headers
    )
    if err:
        return 'err', err
    if status in (200, 204):
        return 'ok', None
    if status == 404:
        return 'not_found', None
    code = body.get('error_code', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
    return 'err', code


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    user_id = config.get('user_id')

    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Выполните авторизацию на вкладке Яндекс')
        return
    if not user_id:
        print('⚠️  Для запуска скрипта не хватает данных: user_id')
        print('ℹ️  Выполните авторизацию на вкладке Яндекс')
        return

    links = parse_links(script_data.get('links'))
    keep_sitemaps = normalize_keep_paths(script_data.get('keep_sitemaps'))

    if not links:
        print('❌ Для запуска скрипта обязателен список сайтов (links).')
        return

    if not keep_sitemaps:
        print('❌ Для запуска скрипта обязателен список сайтмапов для сохранения (keep_sitemaps).')
        return

    headers = {
        'Authorization': f'OAuth {token}',
        'Content-Type': 'application/json'
    }

    print(f'ℹ️  user_id: {user_id}')
    print(f'ℹ️  Сайтов из списка: {len(links)}')
    print(f'ℹ️  Сайтмапов для сохранения: {len(keep_sitemaps)}')
    for p in keep_sitemaps:
        print(f'     - {p}')

    hosts_index = {}

    status, body, err = api_request('GET', f'{BASE_URL}/user/{user_id}/hosts', headers)
    if err:
        print(f'⚠️  Ошибка получения списка сайтов: {err}')
        return
    if status != 200:
        error_msg = body.get('error_message', f'HTTP {status}') if isinstance(body, dict) else f'HTTP {status}'
        print(f'⚠️  Ошибка получения списка сайтов: {error_msg}')
        return

    all_hosts = body.get('hosts', []) if isinstance(body, dict) else []
    for h in all_hosts:
        hid = h.get('host_id', '')
        if not hid:
            continue
        for url_key in ('unicode_host_url', 'ascii_host_url'):
            hostname = normalize_host(h.get(url_key, ''))
            if hostname and hostname not in hosts_index:
                hosts_index[hostname] = hid

    total = len(links)
    kept = deleted = robots = not_found = errors = 0
    processed = 0

    for site in links:
        processed += 1
        hostname = normalize_host(site)
        print(f'ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)')

        if not hostname:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, ["—"], ["—"], ["❌ Невалидный сайт"]]}, ensure_ascii=False)}')
            continue

        host_id = hosts_index.get(hostname)
        if not host_id:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, ["—"], ["—"], ["❌ Не найден в Вебмастере"]]}, ensure_ascii=False)}')
            continue

        sitemaps, list_err = list_sitemaps(user_id, host_id, headers)
        if list_err:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, ["—"], ["—"], [f"❌ {list_err}"]]}, ensure_ascii=False)}')
            continue

        user_sitemaps, user_err = list_user_sitemaps(user_id, host_id, headers)
        if user_err:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, ["—"], ["—"], [f"❌ {user_err}"]]}, ensure_ascii=False)}')
            continue

        if not sitemaps and not user_sitemaps:
            not_found += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, ["—"], ["—"], ["ℹ️ Сайтмапы не найдены"]]}, ensure_ascii=False)}')
            continue

        site_kept = 0
        site_deleted = 0
        site_errors = 0
        robot_paths = []
        user_paths = []
        user_statuses = []

        def is_keep(sm_path):
            return sm_path is not None and sm_path in keep_sitemaps

        # 1) Обработанные sitemap (source WEBMASTER / ROBOTS_TXT)
        for sm in sitemaps:
            sm_url = sm.get('sitemap_url', '')
            sm_path = sitemap_path_of(sm_url)
            sid = sm.get('sitemap_id', '')

            # Из robots.txt (или без источника) — не удаляются
            if not is_webmaster_source(sm):
                if sm_path:
                    robot_paths.append(sm_path)
                else:
                    site_errors += 1
                continue

            user_paths.append(sm_path if sm_path is not None else sm_url)
            if is_keep(sm_path):
                site_kept += 1
                user_statuses.append('✅ Оставлен')
                continue
            if not sid:
                site_errors += 1
                user_statuses.append('❌ Нет sitemap_id')
                continue
            del_status, del_err = delete_sitemap(user_id, host_id, headers, sid)
            if del_status == 'ok':
                site_deleted += 1
                user_statuses.append('🗑 Удалён')
            elif del_status == 'not_found':
                site_deleted += 1
                user_statuses.append('🗑 Удалён (уже отсутствовал)')
            else:
                site_errors += 1
                user_statuses.append(f'❌ {del_err}')
                print(f'⚠️  [sitemap] {hostname} {sm_url} -> ошибка удаления: {del_err}')

        # 2) Добавленные пользователем, ещё не обработанные (user-added-sitemaps).
        #    Те, чей sitemap_id уже есть в /sitemaps, уже обработаны выше — пропускаем.
        processed_ids = {sm.get('sitemap_id', '') for sm in sitemaps if sm.get('sitemap_id')}
        for us in user_sitemaps:
            us_url = us.get('sitemap_url', '')
            us_path = sitemap_path_of(us_url)
            us_id = us.get('sitemap_id', '')

            if us_id and us_id in processed_ids:
                continue

            user_paths.append(us_path if us_path is not None else us_url)
            if is_keep(us_path):
                site_kept += 1
                user_statuses.append('✅ Оставлен')
                continue
            if not us_id:
                site_errors += 1
                user_statuses.append('❌ Нет sitemap_id')
                continue
            del_status, del_err = delete_sitemap(user_id, host_id, headers, us_id)
            if del_status == 'ok':
                site_deleted += 1
                user_statuses.append('🗑 Удалён')
            elif del_status == 'not_found':
                site_deleted += 1
                user_statuses.append('🗑 Удалён (уже отсутствовал)')
            else:
                site_errors += 1
                user_statuses.append(f'❌ {del_err}')
                print(f'⚠️  [user-added] {hostname} {us_url} -> ошибка удаления: {del_err}')

        if site_errors:
            errors += 1

        kept += site_kept
        deleted += site_deleted
        robots += len(robot_paths)

        robot_cell = robot_paths if robot_paths else ["—"]
        user_cell = user_paths if user_paths else ["—"]
        status_cell = user_statuses if user_statuses else ["—"]
        print(f'__TABLE_ROW__:{json.dumps({"cells": [hostname, robot_cell, user_cell, status_cell]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Сайтмапы для сохранения": ", ".join(keep_sitemaps),
        "Оставлено": kept,
        "Удалено": deleted,
        "Файлов из робота": robots,
        "Не найдено": not_found,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()