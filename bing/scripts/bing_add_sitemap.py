"""
bing_add_sitemap.py — добавление sitemap в Bing Webmaster.

Для каждого сайта аккаунта (или из списка links) проверяет наличие sitemap
через GetFeeds и, если его нет, отправляет SubmitFeed.

Вход (../arrays/bing_add_sitemap.json):
    links — сайты (по одному на строку), пусто = все сайты аккаунта.

sitemap_path — обязательный ключ в bing/config.json
(в GUI: Ключи Bing → Путь сайтмапа).

Формат таблицы: Сайт | Сайтмап | Статус.
Сводка: Сайтов | Путь сайтмапа | Успешно | Ошибок.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_add_sitemap"


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


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = script_data()
    links = lines_of(data.get('links'))

    config = bc.load_config()
    sitemap_path = normalize_path(config.get('sitemap_path') or '')
    if not sitemap_path:
        print("❌ Для запуска скрипта нужен sitemap_path (Путь сайтмапа в настройках Bing)")
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

    success = errors = 0
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

        feed_url = f"{site_url.rstrip('/')}{sitemap_path}"

        # Проверяем существующие фиды
        ok, data_feeds, error = bc.call("GetFeeds", {"siteUrl": site_url})
        if not ok:
            errors += 1
            table_row([site_url, feed_url, f"❌ {error}"])
            continue

        feeds = as_list(data_feeds)
        existing = [f for f in feeds if (f.get("Url") or '') == feed_url]

        if existing:
            # Сайтмап уже есть — показываем реальный статус из Bing
            status = existing[0].get("Status", "Unknown")
            table_row([site_url, feed_url, status])
            continue

        # Сайтмапа нет — добавляем через SubmitFeed
        ok, _, error = bc.call("SubmitFeed", body={"siteUrl": site_url, "feedUrl": feed_url})
        if not ok:
            # Если ошибка «уже существует» — считаем успехом
            err = (error or '').lower()
            if any(k in err for k in ('already', 'exist', 'duplicate', 'уже', 'существ')):
                success += 1
                table_row([site_url, feed_url, "⭐ Добавлен ранее"])
            else:
                # Проверка на дневной лимит (ErrorCode 4 = ThrottleUser)
                if 'throttleuser' in err or 'errorcode 4' in err or 'errorcode=4' in err:
                    print(f"⛔ Дневной лимит на добавление сайтмапов исчерпан (ErrorCode 4: ThrottleUser).")
                    print(f"ℹ️  Попробуйте снова завтра. Обработано {processed} из {total} сайтов.")
                    # Выводим частичную сводку и завершаем с кодом 100
                    summary = {
                        "Сайтов": total,
                        "Путь сайтмапа": sitemap_path,
                        "Успешно": success,
                        "Ошибок": errors,
                        "Прервано по лимиту": True,
                    }
                    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
                    print('__TABLE_DONE__:{}')
                    sys.exit(100)
                errors += 1
                table_row([site_url, feed_url, f"❌ {error}"])
        else:
            success += 1
            table_row([site_url, feed_url, "✅ Добавлен"])

    summary = {
        "Сайтов": total,
        "Путь сайтмапа": sitemap_path,
        "Успешно": success,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()