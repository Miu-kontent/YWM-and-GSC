"""
gsc_delete_sitemaps_except.py — удаление всех sitemap, КРОМЕ указанных в списке "keep".

Для каждого сайта из списка links (обязательно) находит все сайтмапы через sitemaps.list,
оставляет только те, чей путь совпадает с одним из keep_sitemaps, остальные удаляет
через sitemaps.delete (DELETE /sites/siteUrl/sitemaps/feedpath).

Вход (google/arrays/gsc_delete_sitemaps_except.json):
    links — сайты (по одному на строке), ОБЯЗАТЕЛЬНО — список сайтов для обработки.
    keep_sitemaps — список путей sitemap, которые нужно ОСТАВИТЬ (не удалять).
        Можно указать 1-3 пути (через перевод строки). Пути можно с / или без.
        Пути сравниваются с полным URL сайтмапа (path из API).

Формат таблицы: Сайт | Сайтмап | Статус.
Сводка: Сайтов | Оставлено | Удалено | Не найдено | Ошибок.
"""
import json
import os
import sys
import time

import gsc_client

QUOTA_WAIT = 10
QUOTA_RETRIES = 10


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_delete_sitemaps_except.json')
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


def normalize_keep_paths(paths):
    """Приводим пути к нормальному виду: начинаются с /, без двойных слешей."""
    out = []
    for p in paths:
        p = str(p).strip()
        if not p:
            continue
        if not p.startswith('/'):
            p = '/' + p
        # убираем возможные // внутри
        while '//' in p:
            p = p.replace('//', '/')
        out.append(p)
    return out


def is_quota_error(e):
    try:
        from googleapiclient.errors import HttpError
        return isinstance(e, HttpError) and int(e.resp.status) in (403, 429)
    except Exception:
        return False


def delete_sitemap(webmasters, site_url, sitemap_path, progress):
    """Удаляет один сайтмап по его path. Возвращает ('ok'|'err', err)."""
    last_err = None
    for attempt in range(1, QUOTA_RETRIES + 1):
        try:
            webmasters.sitemaps().delete(siteUrl=site_url, feedpath=sitemap_path).execute()
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
    keep_sitemaps_raw = data.get('keep_sitemaps')

    if not links:
        print("❌ Для запуска скрипта обязателен список сайтов (links).")
        return

    keep_sitemaps = normalize_keep_paths(keep_sitemaps_raw)
    if not keep_sitemaps:
        print("❌ Для запуска скрипта обязателен список сайтмапов для сохранения (keep_sitemaps).")
        return

    print(f"ℹ️  Аккаунт: ...")
    print(f"ℹ️  Сайтов из списка: {len(links)}")
    print(f"ℹ️  Сайтмапов для сохранения: {len(keep_sitemaps)}")
    for p in keep_sitemaps:
        print(f"     - {p}")

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    print(f"ℹ️  Аккаунт: {auth_info}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    site_entries = sites_res.get('siteEntry', [])

    targets = []
    for raw in links:
        found = gsc_client.resolve_entries(site_entries, raw)
        if not found:
            targets.append((raw, None))
        else:
            e = found[0]
            targets.append((e.get('siteUrl', ''), e))

    total = len(targets)
    print(f"ℹ️  Сайтов обрабатывается: {total}")

    kept = deleted = not_found = errors = 0
    domains = 0
    processed = 0

    for site_url, entry in targets:
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

        if site_url.lower().startswith('sc-domain:'):
            domains += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "ℹ️ Доменный ресурс"]}, ensure_ascii=False)}')
            continue

        try:
            sm_res = webmasters.sitemaps().list(siteUrl=site_url).execute()
        except Exception as e:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", f"❌ {gsc_client.api_error_str(e)}"]}, ensure_ascii=False)}')
            continue

        all_sitemaps = sm_res.get('sitemap', [])
        if not all_sitemaps:
            not_found += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, "—", "ℹ️ Сайтмапы не найдены"]}, ensure_ascii=False)}')
            continue

        # Формируем полные URL сайтмапов, которые нужно ОСТАВИТЬ
        full_keep_urls = [f"{site_url.rstrip('/')}{p}" for p in keep_sitemaps]

        site_kept = 0
        site_deleted = 0
        site_errors = 0

        for sm in all_sitemaps:
            sm_path = sm.get('path') or ''
            matched = sm_path in full_keep_urls

            if matched:
                site_kept += 1
            else:
                # удаляем
                status, err = delete_sitemap(
                    webmasters, site_url, sm_path,
                    f"{processed}/{total} ({round(processed / total * 100)}%)"
                )
                if status == 'ok':
                    site_deleted += 1
                else:
                    site_errors += 1

        if site_errors:
            errors += 1
            status_text = f"⚠️ Удалено {site_deleted}, ошибок {site_errors}"
        else:
            if site_deleted > 0 and site_kept > 0:
                status_text = f"✅ Удалено {site_deleted}, оставлено {site_kept}"
            elif site_deleted > 0:
                status_text = f"✅ Удалено {site_deleted}"
            elif site_kept > 0:
                status_text = f"✅ Оставлено {site_kept}"
            else:
                status_text = "ℹ️ Нет изменений"

        kept += site_kept
        deleted += site_deleted

        print(f'__TABLE_ROW__:{json.dumps({"cells": [site_url, " / ".join(keep_sitemaps), status_text]}, ensure_ascii=False)}')

    summary = {
        "Сайтов": total,
        "Оставлено": kept,
        "Удалено": deleted,
        "Не найдено": not_found,
        "Ошибок": errors,
        "Доменных ресурсов": domains,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()