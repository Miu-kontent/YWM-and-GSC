import json
import os
import sys
import time

import gsc_client

QUOTA_WAIT = 10
QUOTA_RETRIES = 10

MODES = {
    'submit': 'Переотправка',
    'delete_and_submit': 'Удаление + отправка',
}


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_resend_sitemap.json')
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


def api_call(build_fn, progress):
    """Выполняет API-запрос (build_fn() возвращает request) с ретраями при квоте.
    Возвращает ('ok', None) | ('err', str)."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            build_fn().execute()
            return 'ok', None
        except Exception as e:
            last_err = gsc_client.api_error_str(e)
            if is_quota_error(e) and attempt < QUOTA_RETRIES:
                print(f"⏳  Лимит запросов, ждём {QUOTA_WAIT} сек... (попытка {attempt}/{QUOTA_RETRIES}) | Обработка сайтов - {progress}", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            break
    return 'err', last_err


def resolve_sitemap_url(site_url, raw, sitemap_path):
    """
    Строит URL сайтмапа для сайта site_url (scheme://host).
    Если raw — полный URL сайтмапа (оканчивается на sitemap_path) — берём его как есть.
    """
    if not sitemap_path:
        return None
    raw_norm = (raw or '').strip()
    if raw_norm and raw_norm.rstrip('/').endswith(sitemap_path):
        return raw_norm
    return f"{site_url.rstrip('/')}{sitemap_path}"


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = load_data()
    links = parse_links(data.get('links'))
    mode = data.get('mode', 'submit')
    if mode not in MODES:
        mode = 'submit'

    config = gsc_client.load_config()
    sitemap_path = str(config.get('sitemap_path') or '').strip()
    if not sitemap_path:
        print("⚠️  Для запуска скрипта не хватает данных: sitemap_path (Путь сайтмапа в настройках Google)")
        return
    if not sitemap_path.startswith('/'):
        sitemap_path = '/' + sitemap_path

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    print(f"ℹ️  Аккаунт: {auth_info}")
    print(f"ℹ️  Режим: {MODES[mode]}")
    print(f"ℹ️  Путь к sitemap: {sitemap_path}")
    if links:
        print(f"ℹ️  Сайтов из списка: {len(links)}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    site_entries = sites_res.get('siteEntry', [])

    if links:
        targets = []
        for raw in links:
            found = gsc_client.resolve_entries(site_entries, raw)
            if not found:
                targets.append((raw, '', None))
            else:
                targets.append((raw, found[0].get('siteUrl', ''), found[0]))
    else:
        targets = [(s.get('siteUrl', ''), s.get('siteUrl', ''), s) for s in site_entries]

    total = len(targets)
    print(f"ℹ️  Сайтов обрабатывается: {total}")

    success = errors = 0
    domains = 0
    processed = 0

    for raw, site_url, entry in targets:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        if entry is None:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [raw, "—", "❌ Не добавлен в GSC"]}, ensure_ascii=False)}')
            continue

        level = entry.get('permissionLevel', '')
        if level == 'siteUnverifiedUser':
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "❌ Не подтверждён"]}, ensure_ascii=False)}')
            continue

        if site_url.lower().startswith('sc-domain:'):
            domains += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "ℹ️ Доменный ресурс"]}, ensure_ascii=False)}')
            continue

        sitemap_url = resolve_sitemap_url(site_url, raw, sitemap_path)
        if not sitemap_url:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "❌ Пустой путь сайтмапа"]}, ensure_ascii=False)}')
            continue

        site_base = site_url

        if mode == 'delete_and_submit':
            status, err = api_call(
                lambda: webmasters.sitemaps().delete(siteUrl=site_base, feedpath=sitemap_url),
                progress=f"{processed}/{total} ({round(processed / total * 100)}%)"
            )
            if status != 'ok' and err and 'notFound' not in err and '404' not in err:
                errors += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, f"❌ Удаление: {err}"]}, ensure_ascii=False)}')
                continue

        status, err = api_call(
            lambda: webmasters.sitemaps().submit(siteUrl=site_base, feedpath=sitemap_url),
            progress=f"{processed}/{total} ({round(processed / total * 100)}%)"
        )
        if status == 'ok':
            success += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, "✅ Отправлен"]}, ensure_ascii=False)}')
        else:
            low = (err or '').lower()
            if 'already' in low or 'exists' in low:
                success += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, "⭐ Отправлен ранее"]}, ensure_ascii=False)}')
            else:
                errors += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, f"❌ {err}"]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Режим": MODES[mode],
        "Успешно": success,
        "Ошибок": errors,
        "Доменных ресурсов": domains,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()