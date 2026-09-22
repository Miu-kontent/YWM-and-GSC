import json
import os
import sys
import time

import gsc_client

QUOTA_WAIT = 10
QUOTA_RETRIES = 10
VERIFY_METHODS = ["META", "FILE"]


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_verify.json')
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


def is_already_error(e):
    msg = gsc_client.api_error_str(e).lower()
    return ('already exists' in msg) or ('existing webresource' in msg) or ('already verified' in msg)


def verify_site(site_verification, site_url, progress):
    """Возвращает (status, err): 'ok' — подтверждён, 'already' — уже был, 'err' — ошибка."""
    resource = {"site": {"identifier": site_url, "type": "SITE"}}
    last_err = None
    for method in VERIFY_METHODS:
        for attempt in range(1, QUOTA_RETRIES + 1):
            try:
                site_verification.webResource().insert(
                    verificationMethod=method,
                    body=resource
                ).execute()
                return 'ok', method
            except Exception as e:
                last_err = gsc_client.api_error_str(e)
                if is_already_error(e):
                    return 'already', method
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

    webmasters, site_verification, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    existing = {}
    for entry in sites_res.get('siteEntry', []):
        key = gsc_client.property_key(entry.get('siteUrl', ''))
        if key:
            existing[key] = entry.get('permissionLevel', '')

    if links:
        targets = []
        for raw in links:
            site_url = gsc_client.build_site_url(raw)
            if not site_url:
                targets.append(('bad', raw))
                continue
            level = existing.get(gsc_client.property_key(site_url))
            if level is None:
                targets.append(('not_added', site_url))
            elif level == 'siteUnverifiedUser':
                targets.append(('unverified', site_url))
            else:
                targets.append(('verified', site_url))
        print(f"ℹ️  Сайтов из списка: {len(targets)}")
    else:
        targets = []
        for entry in sites_res.get('siteEntry', []):
            site_url = entry.get('siteUrl', '')
            level = entry.get('permissionLevel', '')
            if level == 'siteUnverifiedUser':
                targets.append(('unverified', site_url))
            else:
                targets.append(('verified', site_url))
        print(f"ℹ️  Режим: все сайты из аккаунта ({len(targets)})")

    total = len(targets)
    if not total:
        print("❌ Нет сайтов для обработки!")
        return

    earlier = verified_now = errors = 0
    processed = 0

    for kind, site_url in targets:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        progress = f"{processed}/{total} ({round(processed / total * 100)}%)"

        if kind == 'bad':
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "❌ Неверный формат сайта"]}, ensure_ascii=False)}')
            continue
        if kind == 'not_added':
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "❌ Не добавлен в GSC"]}, ensure_ascii=False)}')
            continue
        if kind == 'verified':
            earlier += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "⭐ Подтверждён ранее"]}, ensure_ascii=False)}')
            continue

        status, info = verify_site(site_verification, site_url, progress)
        if status == 'ok':
            verified_now += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"✅ Подтверждён ({info})"]}, ensure_ascii=False)}')
        elif status == 'already':
            earlier += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "⭐ Подтверждён ранее"]}, ensure_ascii=False)}')
        else:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, f"❌ {info}"]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Подтверждённых ранее": earlier,
        "Подтверждённых": verified_now,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()