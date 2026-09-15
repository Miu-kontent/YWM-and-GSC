import json
import os
import sys
from datetime import date, timedelta
from urllib.parse import urlparse

import gsc_client

MAX_ROWS = 3
DEBUG = False

PERMISSION_LABELS = {
    "siteOwner": "🟢 Владелец",
    "siteFullUser": "🔵 Полный доступ",
    "siteRestrictedUser": "🟡 Ограниченный доступ",
    "siteUnverifiedUser": "⚪ Не подтверждён",
}


def log(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")


def load_data():
    path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'gsc_export_test.json')
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
        return [l.strip() for l in value if str(l).strip()]
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


def main_url_for(site_url):
    if (site_url or '').startswith('sc-domain:'):
        host = site_url[len('sc-domain:'):].strip()
        return f"https://{host}/"
    s = (site_url or '').rstrip('/')
    return (s + '/') if s else ''


def print_table(headers, rows, total_count=None):
    if not rows:
        print("ℹ️  (пусто)")
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    sep = " | ".join("-" * w for w in col_widths)
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))

    print(f"ℹ️  {header_line}")
    print(f"ℹ️  {sep}")
    for row in rows:
        line = " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        print(f"ℹ️  {line}")

    if total_count is not None and total_count > MAX_ROWS:
        print(f"ℹ️  ... и ещё {total_count - MAX_ROWS} элементов")


def print_kv(data, keys=None):
    if not data:
        print("ℹ️  (пусто)")
        return
    if keys is None:
        keys = data.keys()
    for key in keys:
        val = data.get(key)
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)[:300]
        print(f"ℹ️  {key}: {val}")


def export_sites(webmasters, filter_links):
    print()
    print("ℹ️ === sites.list ===")
    print()

    try:
        res = webmasters.sites().list().execute()
    except Exception as e:
        print(f"⚠️  Ошибка: {gsc_client.api_error_str(e)}")
        return []

    sites = res.get('siteEntry', [])
    total_all = len(sites)
    log(f'Всего сайтов от API: {total_all}')

    if filter_links:
        filter_set = {host_of(l) for l in filter_links if host_of(l)}
        log(f'Фильтр ({len(filter_set)} доменов): {filter_set}')
        matched = []
        for s in sites:
            if host_of(s.get('siteUrl', '')) in filter_set:
                matched.append(s)
        not_found = filter_set - {host_of(s.get('siteUrl', '')) for s in matched}
        if not_found:
            print(f"ℹ️  Не найдены в GSC: {', '.join(sorted(not_found))}")
        sites = matched
        print(f"ℹ️  Фильтр: указано {len(filter_links)} сайтов, найдено {len(sites)} из {total_all}")
    else:
        print(f"ℹ️  Всего сайтов: {total_all}")
        print(f"ℹ️  Длинный анализ: первые {MAX_ROWS} (остальные можно уточнить списком links)")

    print()

    rows = []
    for s in sites[:MAX_ROWS]:
        rows.append([
            s.get('siteUrl', ''),
            PERMISSION_LABELS.get(s.get('permissionLevel', ''), s.get('permissionLevel', ''))
        ])

    print_table(["siteUrl", "Права"], rows, total_count=len(sites)) if rows else print("ℹ️  (пусто)")

    return sites[:MAX_ROWS] if not filter_links else sites


def export_site_get(webmasters, site_url):
    print()
    print(f"ℹ️ === sites.get  {site_url} ===")
    print()

    try:
        res = webmasters.sites().get(siteUrl=site_url).execute()
    except Exception as e:
        print(f"⚠️  Ошибка: {gsc_client.api_error_str(e)}")
        return

    print(f"ℹ️  siteUrl: {res.get('siteUrl', '')}")
    level = res.get('permissionLevel', '')
    print(f"ℹ️  permissionLevel: {level} → {PERMISSION_LABELS.get(level, level)}")


def export_sitemaps(webmasters, site_url):
    print()
    print(f"ℹ️ === sitemaps.list  {site_url} ===")
    print()

    try:
        res = webmasters.sitemaps().list(siteUrl=site_url).execute()
    except Exception as e:
        print(f"⚠️  Ошибка: {gsc_client.api_error_str(e)}")
        return

    sitemaps = res.get('sitemap', [])
    print(f"ℹ️  Всего sitemap: {len(sitemaps)}")
    print()

    rows = []
    for s in sitemaps[:MAX_ROWS]:
        contents = s.get('contents', [])
        cnt = ', '.join(f"{c.get('type', '?')}:{c.get('submitted', '?')}" for c in contents) if contents else "-"
        rows.append([
            s.get('path', ''),
            s.get('type', ''),
            str(s.get('isPending', '')),
            str(s.get('isSitemapsIndex', '')),
            s.get('lastSubmitted', '') or '-',
            s.get('lastDownloaded', '') or '-',
            str(s.get('errors', '')),
            str(s.get('warnings', '')),
            cnt
        ])

    print_table(
        ["path", "type", "pending", "index", "lastSubmitted", "lastDownloaded", "errors", "warnings", "contents"],
        rows,
        total_count=len(sitemaps)
    )


def export_analytics(webmasters, site_url, date_from, date_to, search_type):
    print()
    print(f"ℹ️ === searchanalytics.query  {site_url} ===")
    print()

    if not (date_from and date_to):
        end = date.today()
        start = end - timedelta(days=27)
        date_from, date_to = start.isoformat(), end.isoformat()
        print(f"ℹ️  Дата не указана — берём последние 28 дней: {date_from} .. {date_to}")
    else:
        print(f"ℹ️  Период: {date_from} .. {date_to}")

    print(f"ℹ️  Тип выдачи: {search_type}")

    base = {"startDate": date_from, "endDate": date_to, "type": search_type}

    blocks = [
        ("Итог (без разбивки)", {}),
        ("Топ запросов", {"dimensions": ["query"]}),
        ("Топ страниц", {"dimensions": ["page"]}),
        ("Устройства", {"dimensions": ["device"]}),
        ("Страны", {"dimensions": ["country"]}),
        ("По датам", {"dimensions": ["date"]}),
    ]

    for title, extra in blocks:
        print()
        print(f"ℹ️ -- {title} --")
        body = dict(base)
        body.update(extra)
        body["rowLimit"] = MAX_ROWS
        try:
            res = webmasters.searchanalytics().query(siteUrl=site_url, body=body).execute()
        except Exception as e:
            print(f"⚠️  Ошибка: {gsc_client.api_error_str(e)}")
            continue

        rows = res.get('rows', [])
        table_rows = []
        for r in rows:
            keys = '/'.join(r.get('keys') or [])
            ctr = r.get('ctr', 0)
            table_rows.append([
                keys or '-',
                str(r.get('clicks', 0)),
                str(r.get('impressions', 0)),
                f"{ctr * 100:.2f}%",
                f"{r.get('position', 0):.2f}"
            ])

        print_table(["Ключ", "Клики", "Показы", "CTR", "Позиция"], table_rows, total_count=len(rows))

        meta = res.get('metadata') or {}
        if meta.get('first_incomplete_date'):
            print(f"ℹ️  (неполные данные с {meta.get('first_incomplete_date')})")


def export_url_inspection(searchconsole, site_url):
    print()
    print(f"ℹ️ === urlInspection.index.inspect  {site_url} ===")
    print()

    inspect_url = main_url_for(site_url)
    print(f"ℹ️  Проверяемый URL: {inspect_url}")

    try:
        res = searchconsole.urlInspection().index().inspect(body={
            "inspectionUrl": inspect_url,
            "siteUrl": site_url,
        }).execute()
    except Exception as e:
        print(f"⚠️  Ошибка: {gsc_client.api_error_str(e)}")
        return

    result = res.get('inspectionResult') or {}
    link = result.get('inspectionResultLink')
    if link:
        print(f"ℹ️  Ссылка в UI: {link}")

    index = result.get('indexStatusResult') or {}
    if index:
        print()
        print(f"ℹ️  -- indexStatusResult --")
        sitemaps = index.get('sitemap') or []
        refs = index.get('referringUrls') or []
        print_kv(index, keys=[
            "verdict", "coverageState", "pageFetchState", "indexingState",
            "robotsTxtState", "lastCrawlTime", "googleCanonical", "userCanonical",
            "crawledAs", "indexingState", "crawlingAllowed"
        ])
        if sitemaps:
            print(f"ℹ️  sitemaps ({len(sitemaps)}): {', '.join(sitemaps[:5])}")
        if refs:
            print(f"ℹ️  referringUrls ({len(refs)}): {', '.join(refs[:5])}")

    rich = result.get('richResultsResult')
    if rich:
        print()
        print(f"ℹ️  -- richResultsResult --")
        print(f"ℹ️  verdict: {rich.get('verdict', '')}")
        items = rich.get('detectedItems') or []
        print(f"ℹ️  detectedItems: {len(items)}")

    mobile = result.get('mobileUsabilityResult')
    if mobile:
        print()
        print(f"ℹ️  -- mobileUsabilityResult (deprecated) --")
        print_kv(mobile, keys=["verdict", "issues"])
    if not (index or rich or mobile):
        print("ℹ️  (нет данных по проверке)")


def export_site_verification(sv, site_url, cache):
    print()
    print(f"ℹ️ === siteVerification.webResource  {site_url} ===")
    print()

    if cache.get('items') is None:
        try:
            res = sv.webResource().list().execute()
            cache['items'] = res.get('items', [])
        except Exception as e:
            print(f"⚠️  Ошибка: {gsc_client.api_error_str(e)}")
            cache['items'] = []
        log(f'webResource.list → {len(cache["items"])} ресурсов')

    target_host = host_of(site_url)
    if not target_host:
        print("ℹ️  (не удалось распознать хост)")
        return

    found = [i for i in cache['items'] if host_of(i.get('site', {}).get('identifier', '')) == target_host]
    if not found:
        print("ℹ️  Не найден в подтверждённых ресурсах Site Verification")
        return

    for item in found:
        print(f"ℹ️  Ресурс: {item.get('site', {}).get('identifier', '')} (type={item.get('site', {}).get('type', '?')})")
        owners = item.get('owners', [])
        print(f"ℹ️  Владельцы ({len(owners)}): {', '.join(owners) if owners else '-'}")


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ === ЭКСПОРТ ДАННЫХ GOOGLE SEARCH CONSOLE (ТЕСТ) ===")

    data = load_data()

    webmasters, site_verification, searchconsole, auth_info = gsc_client.build_services()
    if not webmasters:
        print()
        print(f"⚠️  {auth_info}")
        print("ℹ️  Авторизуйтесь на вкладке Google → Авторизоваться")
        return

    print()
    print(f"ℹ️  Аккаунт: {auth_info}")

    links = parse_links(data.get('links'))
    date_from = str(data.get('date_from', '') or '').strip()
    date_to = str(data.get('date_to', '') or '').strip()
    search_type = str(data.get('type', 'web') or 'web').strip()

    if links:
        print(f"ℹ️  Сайтов для анализа: {len(links)}")
    if date_from and date_to:
        print(f"ℹ️  date_from: {date_from}, date_to: {date_to}")
    print(f"ℹ️  Тип выдачи: {search_type}")

    sites = export_sites(webmasters, links)

    wr_cache = {}

    for site in sites:
        site_url = site.get('siteUrl', '')
        print()
        print("ℹ️ ─────────────────────────────────────────────")
        print(f"ℹ️  Сайт: {site_url}")
        print("ℹ️ ─────────────────────────────────────────────")

        export_site_get(webmasters, site_url)
        export_sitemaps(webmasters, site_url)
        export_analytics(webmasters, site_url, date_from, date_to, search_type)
        export_url_inspection(searchconsole, site_url)
        export_site_verification(site_verification, site_url, wr_cache)

    print()
    print("ℹ️ === ЭКСПОРТ ЗАВЕРШЁН ===")
    print(f"ℹ️  Сайтов проанализировано: {len(sites)}")


if __name__ == "__main__":
    main()