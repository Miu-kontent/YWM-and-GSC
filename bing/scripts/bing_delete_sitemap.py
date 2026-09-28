"""
bing_delete_sitemap.py — удаление sitemap из Bing Webmaster (API).

Для каждого сайта аккаунта (или из списка links) находит сайтмап по пути
sitemap_path (bing/config.json или поле на странице) и удаляет его
через RemoveFeed.

Вход (../arrays/bing_delete_sitemap.json):
    links         — сайты (по одному на строку), пусто = все сайты аккаунта
    sitemap_path  — путь удаляемого сайтмапа (поле на странице скрипта)
                    Если поле пусто — берётся sitemap_path из bing/config.json

Формат таблицы: Сайт | Сайтмап | Статус.
Сводка: Сайтов | Путь сайтмапа | Удалено | Не найдено | Ошибок.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_delete_sitemap"


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


def normalize_path(path):
    """Путь начинается с /, без двойных слешей."""
    path = (path or '').strip()
    if not path:
        return ''
    if not path.startswith('/'):
        path = '/' + path
    while '//' in path:
        path = path.replace('//', '/')
    return path


def build_site_url(raw):
    """Формат для API: http://host (без пути)."""
    url = (raw or '').strip()
    if not url:
        return None
    if '://' not in url:
        url = 'https://' + url
    host = url.split('://', 1)[1].split('/')[0].split('?')[0]
    return f"http://{host}"


def extract_path(url):
    """Извлекает путь из URL (все после хоста)."""
    if not url:
        return ''
    # Убираем схему
    if '://' in url:
        url = url.split('://', 1)[1]
    # Убираем хост
    parts = url.split('/', 1)
    if len(parts) > 1:
        return '/' + parts[1]
    return '/'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = script_data()
    links = lines_of(data.get('links'))

    config = bc.load_config()
    sitemap_path = normalize_path(data.get('sitemap_path') or config.get('sitemap_path') or '')
    if not sitemap_path:
        print("❌ Для запуска скрипта нужен sitemap_path (поле 'Путь сайтмапа к удалению' или настройки Bing)")
        return

    token, email = bc.get_access_token()
    if not token:
        print(f"❌ {email}")
        return
    bc.set_token(token)
    print(f"ℹ️  Аккаунт: {email}")
    print(f"ℹ️  Путь к sitemap: {sitemap_path}")
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
                targets.append((raw, None))
                continue
            match = next((s for s in all_sites if bc.host_of(s.get("Url")) == bc.host_of(site_url)), None)
            targets.append((site_url, match))
    else:
        targets = [(s.get("Url", ""), s) for s in all_sites if s.get("Url")]

    total = len(targets)
    print(f"ℹ️  Сайтов обрабатывается: {total}")

    deleted = not_found = errors = 0
    processed = 0

    for site_url, site_info in targets:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        if site_info is None:
            errors += 1
            table_row([site_url, "—", "❌ Не найден в Bing"])
            continue

        verified = bool(site_info.get("IsVerified"))
        if not verified:
            errors += 1
            table_row([site_url, "—", "❌ Не подтверждён"])
            continue

        # Ищем фид по пути (сравниваем пути, игнорируя схему http/https)
        target_path = normalize_path(sitemap_path)
        ok, data_feeds, error = bc.call("GetFeeds", {"siteUrl": site_url})
        if not ok:
            errors += 1
            table_row([site_url, target_path, f"❌ {error}"])
            continue

        feeds = as_list(data_feeds)
        matches = [f for f in feeds if extract_path(f.get("Url") or '') == target_path]

        if not matches:
            not_found += 1
            table_row([site_url, target_path, "ℹ️ Не найден"])
            continue

        # Удаляем через RemoveFeed (используем полный URL из фида)
        feed_url = matches[0].get("Url") or ''
        ok, _, error = bc.call("RemoveFeed", body={"siteUrl": site_url, "feedUrl": feed_url})
        if not ok:
            errors += 1
            table_row([site_url, target_path, f"❌ {error}"])
        else:
            deleted += 1
            table_row([site_url, target_path, "✅ Удалён"])

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