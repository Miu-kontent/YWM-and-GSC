"""
bing_add_sitemap.py — добавление sitemap в Bing Webmaster.

Для каждого сайта аккаунта (или из списка links) проверяет наличие sitemap
через GetFeeds и, если его нет, отправляет SubmitFeed. Показывает фактическое
состояние сайтмапа, как gsc_add_sitemap.py:
    ✅ Успешно     — сайтмап есть и обработан Bing
    ✅ Добавлен    — сайтмап только что отправлен
    ⭐ Добавлен ранее — гонка при отправке (сайтмап уже появился)
    ⏳ В обработке — сайтмап есть, но ещё не обработан
    ❌ Ошибка      — сайтмап есть, но с ошибкой
    ❌ Не найден в Bing / ❌ Не подтверждён — структурные проблемы

Вход (../arrays/bing_add_sitemap.json):
    links — сайты (по одному на строку), пусто = все сайты аккаунта.

sitemap_path — обязательный ключ в bing/config.json
(в GUI: Ключи Bing → Путь сайтмапа).

Формат таблицы: Сайт | Сайтмап | Статус.
Сводка: Сайтов | Путь сайтмапа | Успешно | Для переотправки.
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


def summary(total, sitemap_path, success, resend, stopped=False):
    """Единая сводка: и для полного прогона, и для остановки по дневному лимиту."""
    data = {
        "Сайтов": total,
        "Путь сайтмапа": sitemap_path,
        "Успешно": success,
        "Для переотправки": resend,
    }
    if stopped:
        data["Прервано по лимиту"] = True
    return data


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
            match = next((s for s in all_sites if bc.host_of(s.get("Url")) == bc.host_of(raw)), None)
            targets.append((raw, match))
    else:
        targets = [(s.get("Url", ""), s) for s in all_sites if s.get("Url")]

    total = len(targets)
    print(f"ℹ️  Сайтов обрабатывается: {total}")

    success = resend = 0
    processed = 0

    for site_url, site_info in targets:
        processed += 1
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        if site_info is None:
            resend += 1
            table_row([site_url, "—", "❌ Не найден в Bing"])
            continue

        # Работаем с адресом, который отдаёт Bing (со схемой и слешем): собранный
        # из ввода http://host API не узнаёт, и существующий фид не находится.
        site_url = (site_info.get("Url") or site_url).strip()

        verified = bool(site_info.get("IsVerified"))
        if not verified:
            resend += 1
            table_row([site_url, "—", "❌ Не подтверждён"])
            continue

        feed_url = f"{site_url.rstrip('/')}{sitemap_path}"

        # Проверяем существующие фиды
        ok, data_feeds, error = bc.call("GetFeeds", {"siteUrl": site_url})
        if not ok:
            resend += 1
            table_row([site_url, feed_url, f"❌ {error}"])
            continue

        feeds = as_list(data_feeds)
        existing = [f for f in feeds if (f.get("Url") or '') == feed_url]

        if existing:
            # Сайтмап уже есть — показываем реальный статус из Bing
            feed = existing[0]
            table_row([site_url, feed_url, bc.feed_health_label(feed)])
            if bc.feed_needs_resend(feed):
                resend += 1
            else:
                success += 1
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
                    # Частичная сводка и выход с кодом 100
                    print(f'__SUMMARY__:{json.dumps(summary(total, sitemap_path, success, resend, stopped=True), ensure_ascii=False)}')
                    print('__TABLE_DONE__:{}')
                    sys.exit(100)
                resend += 1
                table_row([site_url, feed_url, f"❌ {error}"])
        else:
            success += 1
            table_row([site_url, feed_url, "✅ Добавлен"])

    print(f'__SUMMARY__:{json.dumps(summary(total, sitemap_path, success, resend), ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()