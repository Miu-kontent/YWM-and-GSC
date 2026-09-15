import json
import os
import sys
import time
from urllib.parse import urlparse

import gsc_client

QUOTA_WAIT = 10
QUOTA_RETRIES = 10


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_add_sites.json')
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


def to_site_url(raw):
    raw = (raw or '').strip()
    if not raw:
        return ''
    if raw.lower().startswith('sc-domain:'):
        return f"sc-domain:{raw[len('sc-domain:'):].strip().lower()}"
    host = host_of(raw)
    return f"https://{host}/" if host else ''


def add_site(webmasters, site_url, progress):
    """Возвращает (ok, err). При квоте — ретраи 3×30 сек (как в легаси)."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            webmasters.sites().add(siteUrl=site_url).execute()
            return True, None
        except Exception as e:
            last_err = gsc_client.api_error_str(e)
            try:
                from googleapiclient.errors import HttpError
                is_quota = isinstance(e, HttpError) and int(e.resp.status) in (403, 429)
            except Exception:
                is_quota = False
            if is_quota and attempt < QUOTA_RETRIES:
                print(f"⏳  Лимит запросов, ждём {QUOTA_WAIT} сек... (попытка {attempt}/{QUOTA_RETRIES}) | Обработка сайтов - {progress}", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            break
    return False, last_err


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
    print(f"ℹ️  Сайтов для добавления: {len(links)}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    existing = {}
    for entry in sites_res.get('siteEntry', []):
        existing[host_of(entry.get('siteUrl', ''))] = entry.get('permissionLevel', '')

    total = len(links)
    added = earlier = confirmed = errors = 0
    processed = 0

    for site in links:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")
        site_url = to_site_url(site)
        if not site_url:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "❌ Неверный формат сайта"]}, ensure_ascii=False)}')
            continue

        key = host_of(site_url)
        if key in existing:
            level = existing[key]
            if level == 'siteUnverifiedUser':
                earlier += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "ℹ️ Добавлен ранее"]}, ensure_ascii=False)}')
            else:
                confirmed += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"⭐ Подтверждён"]}, ensure_ascii=False)}')
        else:
            ok, err = add_site(webmasters, site_url, f"{processed}/{total} ({round(processed / total * 100)}%)")
            if ok:
                added += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "✅ Добавлен"]}, ensure_ascii=False)}')
            else:
                errors += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"❌ {err}"]}, ensure_ascii=False)}')

    summary = {
        "Сайты": total,
        "Добавлено": added + earlier,
        "Подтверждено": confirmed,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()