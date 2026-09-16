"""
gsc_add_sitemap.py — добавление sitemap в Google Search Console.

Для каждого сайта аккаунта (или из списка links) проверяет наличие правильного
sitemap через sitemaps.list и, если его нет, отправляет sitemaps.submit.
После проверки показывает фактическое состояние сайтмапа:
    ✅ Успешно    — сайтмап есть и проверен
    ✅ Добавлен   — сайтмап только что отправлен
    ⭐ Добавлен ранее — гонка при отправке (сайтмап уже появился)
    ⏳ В обработке — сайтмап есть, но ещё не обработан Google
    ❌ Ошибка     — сайтмап есть, но с ошибками (errors > 0)
    ❌ Не добавлен в GSC / ❌ Не подтверждён — структурные проблемы

Вход (google/arrays/gsc_add_sitemap.json):
    links — сайты (по одному на строку), пусто = все сайты аккаунта.

sitemap_path — обязательный ключ в google/config.json
(в GUI: Ключи Google → Путь сайтмапа).

Формат таблицы: Сайт | Сайтмап | Статус.
Сводка: Сайтов | Путь сайтмапа | Успешно | Для переотправки.
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
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_add_sitemap.json')
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


def sitemap_health(s):
    """Здоровье сайтмапа: 'ok' | 'pending' | 'error'."""
    try:
        errors = int(s.get('errors') or 0)
    except (TypeError, ValueError):
        errors = 0
    if errors > 0:
        return 'error'
    if s.get('isPending'):
        return 'pending'
    return 'ok'


def health_label(health):
    if health == 'error':
        return "❌ Ошибка"
    if health == 'pending':
        return "⏳ В обработке"
    return "✅ Успешно"


def submit_sitemap(webmasters, site_url, sitemap_url, progress):
    """Возвращает ('ok'|'already'|'error', err). При квоте — ретраи."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            webmasters.sitemaps().submit(siteUrl=site_url, feedpath=sitemap_url).execute()
            return 'ok', None
        except Exception as e:
            last_err = gsc_client.api_error_str(e)
            if is_quota_error(e) and attempt < QUOTA_RETRIES:
                print(f"⏳  Лимит запросов, ждём {QUOTA_WAIT} сек... (попытка {attempt}/{QUOTA_RETRIES}) | Обработка сайтов - {progress}", flush=True)
                time.sleep(QUOTA_WAIT)
                continue
            break
    low = (last_err or '').lower()
    if 'already' in low or 'exists' in low:
        return 'already', None
    return 'error', last_err


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = load_data()
    links = parse_links(data.get('links'))

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

    success = pending = errors = 0
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

        existing = [sm for sm in sm_res.get('sitemap', []) if (sm.get('path') or '') == sitemap_url]
        if existing:
            health = sitemap_health(existing[0])
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, health_label(health)]}, ensure_ascii=False)}')
            if health == 'ok':
                success += 1
            elif health == 'pending':
                pending += 1
            else:
                errors += 1
            continue

        status, err = submit_sitemap(
            webmasters, site_url, sitemap_url,
            f"{processed}/{total} ({round(processed / total * 100)}%)"
        )
        if status == 'ok':
            success += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, "✅ Добавлен"]}, ensure_ascii=False)}')
        elif status == 'already':
            success += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, "⭐ Добавлен ранее"]}, ensure_ascii=False)}')
        else:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, sitemap_url, f"❌ {err}"]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Путь сайтмапа": sitemap_path,
        "Успешно": success,
        "Для переотправки": errors + pending,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()