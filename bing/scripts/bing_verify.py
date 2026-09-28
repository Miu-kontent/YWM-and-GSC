"""
bing_verify.py — подтверждение прав на сайт в Bing Webmaster.

Для каждого сайта (из списка links или все аккаунта) проверяет IsVerified.
Если не подтверждён — вызывает VerifySite.

Вход (../arrays/bing_verify.json):
    links — сайты (по одному на строку), пусто = все сайты аккаунта.

Формат таблицы: Сайт | Статус.
Сводка: Сайтов | Подтверждённых ранее | Подтверждённых | Ошибок.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_verify"


def script_data():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'arrays',
                        f'{SCRIPT_NAME}.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def lines_of(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def as_list(data):
    if isinstance(data, list):
        return [item for item in data if item is not None]
    if isinstance(data, dict):
        return [data]
    return []


def table_row(cells):
    print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}', flush=True)


def build_site_url(raw):
    """Формат для API: http://host (без пути)."""
    url = (raw or '').strip()
    if not url:
        return None
    if '://' not in url:
        url = 'https://' + url
    host = url.split('://', 1)[1].split('/')[0].split('?')[0]
    return f"http://{host}"


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = script_data()
    links = lines_of(data.get('links'))

    token, email = bc.get_access_token()
    if not token:
        print(f"❌ {email}")
        return
    bc.set_token(token)
    print(f"ℹ️  Аккаунт: {email}")
    if links:
        print(f"ℹ️  Сайтов из списка: {len(links)}")

    ok, data_sites, error = bc.call("GetUserSites")
    if not ok:
        print(f"❌ Ошибка GetUserSites: {error}")
        return
    all_sites = as_list(data_sites)

    if links:
        targets = []
        for raw in links:
            site_url = build_site_url(raw)
            if not site_url:
                targets.append(('bad', raw))
                continue
            match = next((s for s in all_sites if bc.host_of(s.get("Url")) == bc.host_of(site_url)), None)
            if match is None:
                targets.append(('not_added', site_url))
            elif match.get("IsVerified"):
                targets.append(('verified', site_url))
            else:
                targets.append(('unverified', site_url))
    else:
        targets = []
        for s in all_sites:
            site_url = s.get("Url", "")
            if not site_url:
                continue
            if s.get("IsVerified"):
                targets.append(('verified', site_url))
            else:
                targets.append(('unverified', site_url))
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

        if kind == 'bad':
            errors += 1
            table_row([site_url, "❌ Неверный формат"])
            continue
        if kind == 'not_added':
            errors += 1
            table_row([site_url, "❌ Не добавлен в Bing"])
            continue
        if kind == 'verified':
            earlier += 1
            table_row([site_url, "⭐ Подтверждён ранее"])
            continue

        # kind == 'unverified' — вызываем VerifySite
        ok, _, error = bc.call("VerifySite", body={"siteUrl": site_url})
        if ok:
            verified_now += 1
            table_row([site_url, "✅ Подтверждён"])
        else:
            errors += 1
            table_row([site_url, f"❌ {error}"])

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