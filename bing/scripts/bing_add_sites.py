"""
bing_add_sites.py — массовое добавление сайтов в Bing Webmaster.

Аналог google/scripts/gsc_add_sites.py: GetUserSites + AddSite.
Повторный AddSite не бросает исключение (по документации), но всё равно
сначала проверяем существующие, чтобы не гонять лишние запросы.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_add_sites"

# Bing API: ошибка 9 = TooManySites (превышен лимит сайтов на аккаунт)
TOO_MANY_SITES_CODE = 9
# Ретраи на троттлинг/сетевые (API уже ретраит, но если превышен лимит аккаунта — не помогает)
RETRIES = 3
RETRY_WAIT = 10


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


def normalize_host(url):
    """Хост в нижнем регистре без схемы/пути — для сравнения."""
    url = (url or '').strip()
    if not url:
        return ''
    if '://' not in url:
        url = 'https://' + url
    host = url.split('://', 1)[1].split('/')[0].split('?')[0]
    return host.lower()


def build_site_url(raw):
    """Формат для AddSite: http://host (как в примере Bing: http://example.com)."""
    host = normalize_host(raw)
    if not host:
        return None
    return f"http://{host}"


def build_site_url_https(raw):
    """Резервный формат: https://host (без слеша)."""
    host = normalize_host(raw)
    if not host:
        return None
    return f"https://{host}"


def is_already_exists_error(error_str):
    """Проверка, что ошибка означает «сайт уже есть»."""
    if not error_str:
        return False
    err = error_str.lower()
    keywords = ('already', 'exist', 'duplicate', 'уже', 'существ', 'добавлен')
    return any(k in err for k in keywords)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = script_data()
    links = lines_of(data.get('links'))

    if not links:
        print("❌ Для запуска скрипта обязателен список сайтов (links)")
        return

    token, email = bc.get_access_token()
    if not token:
        print(f"❌ {email}")
        return
    bc.set_token(token)
    print(f"ℹ️  Аккаунт: {email}")
    print(f"ℹ️  Сайтов для добавления: {len(links)}")

    # 1. Получаем существующие сайты
    ok, data_sites, error = bc.call("GetUserSites")
    if not ok:
        print(f"❌ Ошибка GetUserSites: {error}")
        return
    existing_sites = as_list(data_sites)
    # Сравниваем по хосту (normalize_host убирает схему и путь)
    existing_hosts = {normalize_host(s.get("Url")) for s in existing_sites if s.get("Url")}
    print(f"ℹ️  Уже в Bing: {len(existing_hosts)} сайтов")
    if existing_hosts:
        print(f"ℹ️  Примеры: {', '.join(sorted(list(existing_hosts))[:5])}")

    total = len(links)
    added = earlier = errors = 0
    processed = 0

    for raw in links:
        processed += 1
        site_url = build_site_url(raw)      # пробуем http://host
        site_url_https = build_site_url_https(raw)  # запасной https://host
        if not site_url:
            errors += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [raw, "❌ Неверный формат"]}, ensure_ascii=False)}')
            continue

        host = normalize_host(site_url)
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

        if host in existing_hosts:
            earlier += 1
            table_row([site_url, "ℹ️ Добавлен ранее"])
            continue

        # 2. Добавляем новый сайт — пробуем http, потом https
        ok, data_add, error = bc.call("AddSite", body={"siteUrl": site_url})
        if not ok:
            # Проверка на дневной лимит (ErrorCode 4 = ThrottleUser) — сразу останавливаемся
            err = (error or '').lower()
            if 'throttleuser' in err or 'errorcode 4' in err or 'errorcode=4' in err:
                print(f"⛔ Дневной лимит на добавление сайтов исчерпан (ErrorCode 4: ThrottleUser).")
                print(f"ℹ️  Попробуйте снова завтра. Обработано {processed} из {total} сайтов.")
                summary = {
                    "Сайты": total,
                    "Добавлено": added + earlier,
                    "Ошибок": errors,
                    "Прервано по лимиту": True,
                }
                print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
                print('__TABLE_DONE__:{}')
                sys.exit(100)
            # Если ошибка «уже существует» — считаем как «добавлен ранее»
            if is_already_exists_error(error):
                earlier += 1
                existing_hosts.add(host)
                table_row([site_url, "ℹ️ Добавлен ранее (по ошибке API)"])
                continue
            # Иначе пробуем https://host
            print(f"ℹ️  http не сработал, пробуем https: {site_url_https}", flush=True)
            ok, data_add, error = bc.call("AddSite", body={"siteUrl": site_url_https})
            if not ok:
                err = (error or '').lower()
                if 'throttleuser' in err or 'errorcode 4' in err or 'errorcode=4' in err:
                    print(f"⛔ Дневной лимит на добавление сайтов исчерпан (ErrorCode 4: ThrottleUser).")
                    print(f"ℹ️  Попробуйте снова завтра. Обработано {processed} из {total} сайтов.")
                    summary = {
                        "Сайты": total,
                        "Добавлено": added + earlier,
                        "Ошибок": errors,
                        "Прервано по лимиту": True,
                    }
                    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
                    print('__TABLE_DONE__:{}')
                    sys.exit(100)
                if is_already_exists_error(error):
                    earlier += 1
                    existing_hosts.add(host)
                    table_row([site_url_https, "ℹ️ Добавлен ранее (по ошибке API)"])
                    continue
                errors += 1
                table_row([site_url_https, f"❌ {error}"])
                continue
            site_url = site_url_https  # успех на https

        # Успех
        existing_hosts.add(host)
        added += 1
        table_row([site_url, "✅ Добавлен"])

    summary = {
        "Сайты": total,
        "Добавлено": added + earlier,
        "Подтверждено": 0,
        "Ошибок": errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()