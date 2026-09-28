"""
bing_export.py — основная выгрузка данных Bing Webmaster (только чтение).

Аналог google/scripts/gsc_export.py: два метода — GetUserSites и GetFeeds.
    GetUserSites — список сайтов аккаунта с признаком IsVerified → колонка «Права»
    GetFeeds     — фиды/сайтмапы конкретного сайта → колонки «Сайтмапы» и «Статусы»

Вход (../arrays/bing_export.json):
    links         — сайт(ы) для выгрузки; пусто → все сайты из GetUserSites
    show_sitemaps — чекбокс «Сайтмапы»: показывать колонки с фидами (GetFeeds)

Протокол вывода: __TABLE_ROW__ / __SUMMARY__ / __TABLE_DONE__ (+ __DEBUG__ от bing_client).

Требования: bing/config.json → active_account, bing/accounts.json → токены.
Токен обновляется автоматически (см. bing_client.get_access_token).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_export"


# ======================== ВВОД/ВЫВОД ========================

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


# ======================== ЛОГИКА ========================

def rights_label(site):
    """В Bing у Site нет уровня доступа (как permissionLevel в GSC) — только IsVerified."""
    return "✅ Подтверждён" if site.get("IsVerified") else "❌ Не подтверждён"


def feed_status(status):
    """Строка Status из Bing (в живом прогоне встречались Success и Failed) → подпись."""
    text = str(status or '').strip()
    low = text.lower()
    if not text:
        return "—"
    if 'success' in low:
        return "✅ Успешно"
    if 'fail' in low or 'error' in low:
        return "❌ Ошибка"
    if any(word in low for word in ('pend', 'wait', 'process', 'submit', 'progress', 'index')):
        return "⏳ В обработке"
    return f"ℹ️ {text}"


def is_status_ok(status):
    return 'success' in str(status or '').strip().lower()


def is_status_pending(status):
    low = str(status or '').strip().lower()
    return not is_status_ok(status) and 'fail' not in low and 'error' not in low


def pick_sites(all_sites, links):
    """Сопоставление поля «Сайты» с GetUserSites по хосту (схема и слеши не важны)."""
    if not links:
        return list(all_sites)
    wanted = {bc.host_of(l) for l in links if bc.host_of(l)}
    picked = [s for s in all_sites if bc.host_of(s.get("Url")) in wanted]
    return picked


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    data = script_data()
    links = lines_of(data.get('links'))
    show_sitemaps = bool(data.get('show_sitemaps'))

    token, email = bc.get_access_token()
    if not token:
        print(f"❌ {email}")
        return
    bc.set_token(token)
    print(f"ℹ️  Аккаунт: {email}")
    print(f"ℹ️  Сайтмапы: {'включены' if show_sitemaps else 'выключены'}")
    if links:
        print(f"ℹ️  Сайтов для анализа: {len(links)}")

    ok, data_sites, error = bc.call("GetUserSites")
    if not ok:
        print(f"❌ Ошибка GetUserSites: {error}")
        return
    all_sites = as_list(data_sites)

    if links:
        sites = pick_sites(all_sites, links)
        found = {bc.host_of(s.get("Url")) for s in sites}
        not_found = [l for l in links if bc.host_of(l) not in found]
        if not_found:
            print(f"ℹ️  Не найдены в Bing: {', '.join(not_found)}")
    else:
        sites = list(all_sites)

    total = len(sites)
    print(f"ℹ️  Сайтов анализируется: {total}")
    if not total:
        print("❌ Нет сайтов для выгрузки")
        return

    unverified = feeds_total = no_sitemaps = bad_sites = pending_sites = errors = 0

    for index, site in enumerate(sites, 1):
        site_url = (site.get("Url") or "").strip()
        cells = [site_url, rights_label(site)]

        if show_sitemaps:
            verified = bool(site.get("IsVerified"))
            if not verified:
                unverified += 1
                cells += [["—"], ["—"]]
            else:
                ok, data_feeds, error = bc.call("GetFeeds", {"siteUrl": site_url})
                if not ok:
                    errors += 1
                    bc.dbg("EXPORT", "GetFeeds не отработал", site=site_url, detail=error)
                    cells += [["—"], ["❌ Ошибка"]]
                else:
                    feeds = as_list(data_feeds)
                    feeds_total += len(feeds)
                    if not feeds:
                        no_sitemaps += 1
                        cells += [["—"], ["—"]]
                    else:
                        paths = [(f.get("Url") or "?") for f in feeds]
                        statuses = [feed_status(f.get("Status")) for f in feeds]
                        cells += [paths, statuses]
                        if any(f.get("Status") and not is_status_ok(f.get("Status")) for f in feeds):
                            if any(is_status_pending(f.get("Status")) for f in feeds):
                                pending_sites += 1
                            else:
                                bad_sites += 1

        print(f"ℹ️  Обработка сайтов - {index}/{total} ({round(index / total * 100)}%)")
        table_row(cells)

    summary = {"Сайтов": total, "Не подтверждённых": unverified}
    if show_sitemaps:
        summary["Сайтмапов"] = feeds_total
        summary["Без сайтмапа"] = no_sitemaps
        summary["Сайтов с ошибкой сайтмапа"] = bad_sites
        summary["Сайтов в обработке"] = pending_sites
        summary["Ошибок запросов"] = errors

    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()