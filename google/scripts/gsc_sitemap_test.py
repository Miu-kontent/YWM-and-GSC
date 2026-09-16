import json
import os
import sys
from urllib.parse import urlparse

import gsc_client


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_sitemap_test.json')
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


def sitemap_status(s):
    try:
        errors = int(s.get('errors') or 0)
    except (TypeError, ValueError):
        errors = 0
    if errors > 0:
        return 'error'
    if s.get('isPending'):
        return 'pending'
    return 'ok'


def status_label(st):
    if st == 'error':
        return "❌ Ошибка"
    if st == 'pending':
        return "⏳ В обработке"
    return "✅ Успешно"


def contents_text(sm):
    """Содержимое сайтмапа как в тестовой выгрузке: 'тип:submitted' через запятую (например 'web:103')."""
    contents = sm.get('contents') or []
    if not contents:
        return '-'
    return ', '.join(f"{c.get('type', '?')}:{c.get('submitted', '?')}" for c in contents)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ Запуск: тестовая проверка сайтмапов GSC...")

    data = load_data()
    links = parse_links(data.get('links'))

    webmasters, _, _, auth_info = gsc_client.build_services()
    if not webmasters:
        print(f"⚠️  {auth_info}")
        return

    print(f"ℹ️  Аккаунт: {auth_info}")
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

    unverified = 0
    err_sites = 0
    pending_sites = 0
    sitemaps_total = 0
    fail_count = 0
    processed = 0

    for s in sites:
        processed += 1
        site_url = s.get('siteUrl', '')
        level = s.get('permissionLevel', '')

        if level == 'siteUnverifiedUser':
            unverified += 1
            print(f"__TABLE_ROW__:{json.dumps({'cells': [site_url, ['—'], ['—'], ['—'], ['—'], ['—']]}, ensure_ascii=False)}")
            print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")
            continue

        try:
            sm_res = webmasters.sitemaps().list(siteUrl=site_url).execute()
        except Exception as e:
            fail_count += 1
            err = gsc_client.api_error_str(e)
            print(f"__TABLE_ROW__:{json.dumps({'cells': [site_url, ['—'], [f'❌ {err}'], ['—'], ['—'], ['—']]}, ensure_ascii=False)}")
            print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")
            continue

        sitemaps = sm_res.get('sitemap', [])
        sitemaps_total += len(sitemaps)

        if not sitemaps:
            cells = [site_url, ['—'], ['—'], ['—'], ['—'], ['—']]
        else:
            paths = []
            statuses = []
            errors = []
            warnings = []
            contents = []
            has_err = False
            has_pending = False
            for sm in sitemaps:
                st = sitemap_status(sm)
                has_err = has_err or (st == 'error')
                has_pending = has_pending or (st == 'pending')
                paths.append(sm.get('path') or '?')
                statuses.append(status_label(st))
                errors.append(str(sm.get('errors')) if sm.get('errors') is not None else '-')
                warnings.append(str(sm.get('warnings')) if sm.get('warnings') is not None else '-')
                contents.append(contents_text(sm))

            if has_err:
                err_sites += 1
            if has_pending:
                pending_sites += 1

            cells = [site_url, paths, statuses, errors, warnings, contents]

        print(f"__TABLE_ROW__:{json.dumps({'cells': cells}, ensure_ascii=False)}")
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

    summary = {
        "Сайтов": total,
        "Не подтверждённых": unverified,
        "Сайтмапов": sitemaps_total,
        "Сайтов с ошибками": err_sites,
        "Сайтов с pending": pending_sites,
        "Ошибок запросов": fail_count,
    }
    print(f"__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}")
    print("__TABLE_DONE__:{}")

    print("ℹ️ Готово")


if __name__ == "__main__":
    main()