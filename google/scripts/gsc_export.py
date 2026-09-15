"""
gsc_export.py — выгрузка сайтов Google Search Console.

Основной запрос — sites.list (права). При включённом чекбоксе «Сайтмапы» для
каждого ПОДТВЕРЖДЁННОГО сайта дополнительно sitemaps.list.

⚠️ ВАЖНО: для неподтверждённого сайта любые запросы вернут 403, поэтому
sitemaps.list для них НЕ вызывается (в таблице — прочерки).

Входные данные (google/arrays/gsc_export.json):
    links           — сайты для фильтрации. Пусто = все сайты
    show_sitemaps   — boolean, включать сайтмапы

Сводка (динамические ключи — без summaryRows в реестре):
    Сайтов, Не подтверждённых,
    Без правильного сайтмапа / С неправильными сайтмапами /
    Правильный сайтмап с плохим статусом (только при show_sitemaps)
"""
import json
import os
import sys
from urllib.parse import urlparse

import gsc_client

PERMISSION_LABELS = {
    "siteOwner": "🟢 Владелец",
    "siteFullUser": "🔵 Полный доступ",
    "siteRestrictedUser": "🟡 Ограниченный доступ",
    "siteUnverifiedUser": "⚪ Не подтверждён",
}

DEFAULT_SITEMAP_PATH = "/sitemap/"


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_export.json')
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


def is_bad_sitemap(s):
    return bool(s.get('isPending') is True or s.get('errors') or s.get('warnings'))


def sitemap_status_label(s, expected):
    correct = (s.get('path') or '') == expected
    bad = is_bad_sitemap(s)
    if correct and not bad:
        return "✅"
    if correct and bad:
        return "❌ плохой статус"
    if not correct and bad:
        return "⚠️ плохой статус"
    return "ℹ️"


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ === ВЫГРУЗКА GOOGLE SEARCH CONSOLE ===")

    data = load_data()
    links = parse_links(data.get('links'))
    show_sitemaps = bool(data.get('show_sitemaps'))

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print()
        print(f"⚠️  {auth_info}")
        print("ℹ️  Авторизуйтесь на вкладке Google → Авторизоваться")
        return

    print()
    print(f"ℹ️  Аккаунт: {auth_info}")
    print(f"ℹ️  Сайтмапы: {'включены' if show_sitemaps else 'выключены'}")
    if links:
        print(f"ℹ️  Сайтов для анализа: {len(links)}")

    try:
        sites_res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"❌ Ошибка sites.list: {gsc_client.api_error_str(e)}")
        return

    sites = sites_res.get('siteEntry', [])

    if links:
        filter_set = {host_of(l) for l in links if host_of(l)}
        sites = [s for s in sites if host_of(s.get('siteUrl', '')) in filter_set]
        not_found = filter_set - {host_of(s.get('siteUrl', '')) for s in sites}
        if not_found:
            print(f"ℹ️  Не найдены в GSC: {', '.join(sorted(not_found))}")

    total = len(sites)
    print(f"ℹ️  Сайтов анализируется: {total}")
    print()

    config = gsc_client.load_config()
    sitemap_path = str(config.get('sitemap_path') or DEFAULT_SITEMAP_PATH).strip()
    if not sitemap_path.startswith('/'):
        sitemap_path = '/' + sitemap_path

    unverified = no_correct = wrong_sites = correct_bad = 0

    for s in sites:
        site_url = s.get('siteUrl', '')
        level = s.get('permissionLevel', '')
        rights = PERMISSION_LABELS.get(level, level)

        cells = [site_url, rights]

        if not show_sitemaps:
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        is_unverified = (level == 'siteUnverifiedUser')
        if is_unverified:
            unverified += 1
            cells += [["—"], ["—"]]
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        try:
            sm_res = webmasters.sitemaps().list(siteUrl=site_url).execute()
        except Exception as e:
            cells += [["—"], [f"❌ {gsc_client.api_error_str(e)}"]]
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        sitemaps = sm_res.get('sitemap', [])
        expected = f"{site_url.rstrip('/')}{sitemap_path}"

        paths = [sm.get('path', '') or '?' for sm in sitemaps]
        statuses = [sitemap_status_label(sm, expected) for sm in sitemaps]

        if not sitemaps:
            no_correct += 1
            paths, statuses = ["—"], ["—"]
        else:
            correct_maps = [sm for sm in sitemaps if (sm.get('path') or '') == expected]
            wrong_maps = [sm for sm in sitemaps if (sm.get('path') or '') != expected]
            if not correct_maps:
                no_correct += 1
            if wrong_maps:
                wrong_sites += 1
            if any(is_bad_sitemap(sm) for sm in correct_maps):
                correct_bad += 1

        cells += [paths, statuses]
        print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')

    summary = {"Сайтов": total, "Не подтверждённых": unverified}
    if show_sitemaps:
        summary["Без правильного сайтмапа"] = no_correct
        summary["С неправильными сайтмапами"] = wrong_sites
        summary["Правильный сайтмап с плохим статусом"] = correct_bad

    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == "__main__":
    main()