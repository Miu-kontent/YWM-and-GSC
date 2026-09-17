"""
gsc_delete_sitemap.py — удаление sitemap из Google Search Console (API).

Для каждого сайта аккаунта (или из списка links) находит сайтмап по пути
sitemap_path (google/config.json) и удаляет его через sitemaps.delete
(DELETE /sites/siteUrl/sitemaps/feedpath).

Вход (google/arrays/gsc_delete_sitemap.json):
    links — сайты (по одному на строку), пусто = все сайты аккаунта.
    sitemap_path — путь удаляемого сайтмапа (поле на странице скрипта).
        Если поле пусто — берётся sitemap_path из google/config.json.

Формат таблицы: Сайт | Сайтмап | Статус.
Сводка: Сайтов | Путь сайтмапа | Удалено | Не найдено | Ошибок.
"""
import json
import os
import sys
import time
from urllib.parse import urlparse

import gsc_client

QUOTA_WAIT = 10
QUOTA_RETRIES = 10


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_delete_sitemap.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def parse_links(value):
    if isinstance(value, str):
        return [l.strip() for l in value.strip().split('\n') if l.strip()]
    if isinstance(value, list):
        return [str(l).strip() for l in value if str(l).strip()]
    return []


def host_of(url):
    url = (url or '').strip()
    if not url:
        return ''
    if url.startswith('sc-domain:'):
        url = url[len('sc-domain:'):]
    if '://' not in url:
        url = 'https://' + url
    return (urlparse(url).hostname or '').lower()


def is_quota_error(e):
    try:
        from googleapiclient.errors import HttpError
        return isinstance(e, HttpError) and int(e.resp.status) in (403, 429)
    except Exception:
        return False


def delete_sitemap(webmasters, site_url, sitemap_url, progress):
    """Удаляет сайтмап. Возвращает ('ok'|'err', err). При квоте — ретраи."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            webmasters.sitemaps().delete(siteUrl=site_url, feedpath=sitemap_url).execute()
            return 'ok', None
        except Exception as e:
            last_err = gsc_client.api_error_str(e)
            if is_quota_error(e) and attempt < QUOTA_RETRIES:
                print(f"⏳  Лимит запросов, ждём {QUOTA_WAIT} сек... (попытка {attempt}/{QUOTA_RETRIES}) | Обработка сайтов - {progress}", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            break
    return 'err', last_err


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = load_data()
    links = parse_links(data.get('links'))

    config = gsc_client.load_config()
    sitemap_path = str(data.get('sitemap_path') or config.get('sitemap_path') or '').strip()
    if not sitemap_path:
        print("⚠️  Для запуска скрипта не хватает данных: sitemap_path (поле 'Путь сайтмапа к удалению' или настройки Google)")
        return
    if not sitemap_path.startswith('/'):
        sitemap_path = '/' + sitemap_path

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    print(f"ℹ️  Аккаунт: {auth_info}")
    print(f"ℹ️  Путь к sitemap: {sitemap_path}")
    if links:
        print(f"ℹ️  Сайтов из списка: {len(links)}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    site_entries = sites_res.get('siteEntry', [])
    by_host = {host_of(s.get('siteUrl', '')): s for s in site_entries}

    if links:
        targets = []
        for raw in links:
            h = host_of(raw)
            entry = by_host.get(h)
            if entry is None:
                targets.append((raw, h, None))
            else:
                targets.append((entry.get('siteUrl', ''), h, entry))
    else:
        targets = [(s.get('siteUrl', ''), host_of(s.get('siteUrl', '')), s) for s in site_entries]

    total = len(targets)
    print(f"ℹ️  Сайтов обрабатывается: {total}")

    deleted = not_found = errors = 0
    processed = 0

    for site_url, h, entry in targets:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        if entry is None:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "❌ Не добавлен в GSC"]}, ensure_ascii=False)}')
            continue

        level = entry.get('permissionLevel', '')
        if level == 'siteUnverifiedUser':
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "❌ Не подтверждён"]}, ensure_ascii=False)}')
            continue

        sitemap_url = f"{site_url.rstrip('/')}{sitemap_path}"

        try:
            sm_res = webmasters.sitemaps().list(siteUrl=site_url).execute()
        except Exception as e:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, f"❌ {gsc_client.api_error_str(e)}"]}, ensure_ascii=False)}')
            continue

        matches = [sm for sm in sm_res.get('sitemap', []) if (sm.get('path') or '') == sitemap_url]
        if not matches:
            not_found += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, "ℹ️ Не найден"]}, ensure_ascii=False)}')
            continue

        site_removed = 0
        site_errors = 0
        for sm in matches:
            status, err = delete_sitemap(
                webmasters, site_url, sm.get('path', '') or sitemap_url,
                f"{processed}/{total} ({round(processed / total * 100)}%)"
            )
            if status == 'ok':
                site_removed += 1
            else:
                site_errors += 1

        if site_errors:
            errors += 1
            status_text = f"⚠️ Удалено {site_removed}, ошибок {site_errors}"
        else:
            deleted += 1
            status_text = "✅ Удалён" if site_removed == 1 else f"✅ Удалён ({site_removed})"

        print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, status_text]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Путь сайтмапа": sitemap_path,
        "Удалено": deleted,
        "Не найдено": not_found,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()