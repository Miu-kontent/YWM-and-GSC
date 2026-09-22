"""
gsc_delete_sites.py — удаление сайтов из Google Search Console (API).

Для каждого сайта из списка links находит ресурс в аккаунте (sites.list) и
удаляет его через sites.delete (DELETE /sites/siteUrl).

Вход (google/arrays/gsc_delete_sites.json):
    links — сайты для удаления (по одному на строку). Обязателен.

Формат таблицы: Сайт | Статус.
Сводка: Сайтов | Удалено | Не найдено | Ошибок.
"""
import json
import os
import sys
import time

import gsc_client

QUOTA_WAIT = 10
QUOTA_RETRIES = 10


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_delete_sites.json')
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


def is_quota_error(e):
    try:
        from googleapiclient.errors import HttpError
        return isinstance(e, HttpError) and int(e.resp.status) in (403, 429)
    except Exception:
        return False


def delete_site(webmasters, site_url, progress):
    """Возвращает ('ok'|'gone'|'err', err). При квоте — ретраи."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            webmasters.sites().delete(siteUrl=site_url).execute()
            return 'ok', None
        except Exception as e:
            last_err = gsc_client.api_error_str(e)
            if is_quota_error(e) and attempt < QUOTA_RETRIES:
                print(f"⏳  Лимит запросов, ждём {QUOTA_WAIT} сек... (попытка {attempt}/{QUOTA_RETRIES}) | Обработка сайтов - {progress}", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            break
    low = (last_err or '').lower()
    if 'notfound' in low.replace(' ', '') or '404' in low:
        return 'gone', last_err
    return 'err', last_err


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = load_data()
    links = parse_links(data.get('links'))

    if not links:
        print("⚠️  Для запуска скрипта не хватает данных: links")
        return

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    print(f"ℹ️  Аккаунт: {auth_info}")
    print(f"ℹ️  Сайтов для удаления: {len(links)}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    existing = {}
    for entry in sites_res.get('siteEntry', []):
        key = gsc_client.property_key(entry.get('siteUrl', ''))
        if key and key not in existing:
            existing[key] = entry.get('siteUrl', '')

    total = len(links)
    deleted = not_found = errors = 0
    processed = 0

    for site in links:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")
        site_url = existing.get(gsc_client.property_key(site)) or ''
        if not site_url:
            not_found += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "ℹ️ Не найден в GSC"]}, ensure_ascii=False)}')
            continue

        status, err = delete_site(webmasters, site_url, f"{processed}/{total} ({round(processed / total * 100)}%)")
        if status in ('ok', 'gone'):
            deleted += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "✅ Удалён"]}, ensure_ascii=False)}')
        else:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"❌ {err}"]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Удалено": deleted,
        "Не найдено": not_found,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()