"""
bing_delete_sitemaps_except.py — удаление всех sitemap, КРОМЕ указанных в списке "keep".

Для каждого сайта из списка links (обязательно) находит все сайтмапы через GetFeeds,
оставляет только те, чей URL совпадает с одним из keep_sitemaps, остальные удаляет
через RemoveFeed.

Вход (../arrays/bing_delete_sitemaps_except.json):
    links          — сайты (по одному на строке), ОБЯЗАТЕЛЬНО
    keep_sitemaps  — список путей sitemap (относительно хоста), которые нужно ОСТАВИТЬ
                     Можно указать несколько путей (через перевод строки).
                     Пути сравниваются с полным URL фида (Url из API GetFeeds).

Формат таблицы: Сайт | Оставляемые сайтмапы | Статус.
Сводка: Сайтов | Оставлено | Удалено | Не найдено | Ошибок.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_delete_sitemaps_except"


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


def normalize_keep_paths(paths):
    """Приводим пути к нормальному виду: начинаются с /, без двойных слешей."""
    out = []
    for p in paths:
        p = str(p).strip()
        if not p:
            continue
        if not p.startswith('/'):
            p = '/' + p
        while '//' in p:
            p = p.replace('//', '/')
        out.append(p)
    return out


def extract_path(url):
    """Извлекает путь из URL (все после хоста)."""
    if not url:
        return ''
    if '://' in url:
        url = url.split('://', 1)[1]
    parts = url.split('/', 1)
    if len(parts) > 1:
        return '/' + parts[1]
    return '/'


def has_www(url):
    """Проверяет, есть ли www. в хосте URL."""
    if not url:
        return False
    if '://' in url:
        host = url.split('://', 1)[1].split('/')[0]
    else:
        host = url.split('/')[0]
    return host.startswith('www.')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = script_data()
    links = lines_of(data.get('links'))
    keep_sitemaps_raw = data.get('keep_sitemaps')
    delete_www = bool(data.get('delete_www'))

    if not links:
        print("❌ Для запуска скрипта обязателен список сайтов (links).")
        return

    keep_sitemaps = normalize_keep_paths(keep_sitemaps_raw)
    if not keep_sitemaps:
        print("❌ Для запуска скрипта обязателен список сайтмапов для сохранения (keep_sitemaps).")
        return

    token, email = bc.get_access_token()
    if not token:
        print(f"❌ {email}")
        return
    bc.set_token(token)
    print(f"ℹ️  Аккаунт: {email}")
    print(f"ℹ️  Сайтов из списка: {len(links)}")
    print(f"ℹ️  Сайтмапов для сохранения: {len(keep_sitemaps)}")
    for p in keep_sitemaps:
        print(f"     - {p}")

    ok, data_sites, error = bc.call("GetUserSites")
    if not ok:
        print(f"❌ Ошибка GetUserSites: {error}")
        return
    all_sites = as_list(data_sites)

    targets = []
    seen_hosts = set()
    for raw in links:
        host = bc.host_of(raw)
        if not host or host in seen_hosts:   # один домен не обрабатываем дважды
            continue
        seen_hosts.add(host)
        match = next((s for s in all_sites if bc.host_of(s.get("Url")) == host), None)
        targets.append((raw, match))

    total = len(targets)
    print(f"ℹ️  Сайтов обрабатывается: {total}")

    kept = deleted = not_found = errors = 0
    processed = 0

    for site_url, site_info in targets:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        if site_info is None:
            errors += 1
            table_row([site_url, "—", "❌ Не найден в Bing"])
            continue

        # Адрес берём из GetUserSites: пересобранный из ввода http://host
        # API не узнаёт, и фиды такого сайта не найдутся.
        site_url = (site_info.get("Url") or site_url).strip()

        verified = bool(site_info.get("IsVerified"))
        if not verified:
            errors += 1
            table_row([site_url, "—", "❌ Не подтверждён"])
            continue

        ok, data_feeds, error = bc.call("GetFeeds", {"siteUrl": site_url})
        if not ok:
            errors += 1
            table_row([site_url, "—", f"❌ {error}"])
            continue

        feeds = as_list(data_feeds)
        if not feeds:
            not_found += 1
            table_row([site_url, "—", "ℹ️ Сайтмапы не найдены"])
            continue

        # Формируем множество путей для сохранения (сравниваем по путям, игнорируя схему)
        keep_paths = set(normalize_keep_paths(keep_sitemaps))

        site_kept = 0
        site_deleted = 0
        site_errors = 0
        total_feeds = len(feeds)

        for idx, feed in enumerate(feeds, 1):
            if total_feeds > 2:
                print(f"ℹ️  {site_url}: фид {idx}/{total_feeds}", flush=True)
            feed_url = feed.get("Url") or ''
            feed_path = extract_path(feed_url)
            matched = feed_path in keep_paths

            # Если delete_www включён и фид имеет www. в хосте — не сохраняем, удаляем
            if matched and delete_www and has_www(feed_url):
                matched = False

            if matched:
                site_kept += 1
            else:
                # удаляем
                ok, _, error = bc.call("RemoveFeed", body={"siteUrl": site_url, "feedUrl": feed_url})
                if ok:
                    site_deleted += 1
                else:
                    site_errors += 1
                    bc.dbg("DELETE_EXCEPT", "RemoveFeed ошибка", site=site_url, feed=feed_url, error=error)

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

        table_row([site_url, " / ".join(keep_sitemaps), status_text])

    summary = {
        "Сайтов": total,
        "Оставлено": kept,
        "Удалено": deleted,
        "Не найдено": not_found,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()