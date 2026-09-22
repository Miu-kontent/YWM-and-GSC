import json
import os
import sys
import time

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


def is_quota_error(e):
    try:
        from googleapiclient.errors import HttpError
        return isinstance(e, HttpError) and int(e.resp.status) in (403, 429)
    except Exception:
        return False


def is_limit_error(e):
    """Лимит ~1000 сайтов на аккаунт — Google отдаёт reason='quotaExceeded' (403)."""
    try:
        from googleapiclient.errors import HttpError
        if not isinstance(e, HttpError):
            return False
        data = json.loads(e.content.decode('utf-8'))
        err = data.get('error', {})
        for item in (err.get('errors') or []):
            if item.get('reason') == 'quotaExceeded':
                return True
    except Exception:
        pass
    return False


def add_site(webmasters, site_url, progress):
    """Возвращает (ok, err, limit). При квоте — ретраи, при лимите сайтов — стоп без ретраев."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            webmasters.sites().add(siteUrl=site_url).execute()
            return True, None, False
        except Exception as e:
            last_err = gsc_client.api_error_str(e)
            if is_limit_error(e):
                return False, last_err, True
            if is_quota_error(e) and attempt < QUOTA_RETRIES:
                print(f"⏳  Лимит запросов, ждём {QUOTA_WAIT} сек... (попытка {attempt}/{QUOTA_RETRIES}) | Обработка сайтов - {progress}", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            break
    return False, last_err, False


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
        key = gsc_client.property_key(entry.get('siteUrl', ''))
        if key and key not in existing:
            existing[key] = entry.get('permissionLevel', '')

    total = len(links)
    added = earlier = confirmed = errors = 0
    processed = 0

    need_add = 0
    for site in links:
        k = gsc_client.property_key(gsc_client.build_site_url(site))
        if k and k not in existing:
            need_add += 1
    if len(existing) >= 1000 and need_add > 0:
        print(f"⛔ Лимит сайтов аккаунта достигнут ({len(existing)} >= 1000). Добавление {need_add} новых невозможно.")
        return

    for site in links:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")
        site_url = gsc_client.build_site_url(site)
        if not site_url:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, "❌ Неверный формат сайта"]}, ensure_ascii=False)}')
            continue

        key = gsc_client.property_key(site_url)
        if key in existing:
            level = existing[key]
            if level == 'siteUnverifiedUser':
                earlier += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "ℹ️ Добавлен ранее"]}, ensure_ascii=False)}')
            else:
                confirmed += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"⭐ Подтверждён"]}, ensure_ascii=False)}')
        else:
            ok, err, limit = add_site(webmasters, site_url, f"{processed}/{total} ({round(processed / total * 100)}%)")
            if limit:
                errors += 1
                print(f"⛔ Лимит сайтов аккаунта (~1000) достигнут. Дальнейшее добавление невозможно.")
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"❌ {err}"]}, ensure_ascii=False)}')
                break
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