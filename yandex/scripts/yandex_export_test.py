import json
import os
import sys
import requests


BASE_URL = "https://api.webmaster.yandex.net/v4"
MAX_ROWS = 3
DEBUG = False


def log(msg):
    if DEBUG:
        print(f'[DEBUG] {msg}')


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)


def load_script_data():
    array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'yandex_export_test.json')
    if not os.path.exists(array_path):
        return {}
    try:
        with open(array_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def api_get(url, headers, params=None):
    try:
        log(f'GET {url}')
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        log(f'  → {resp.status_code}')
        if resp.status_code == 200:
            return resp.json(), None
        try:
            err_body = resp.json()
            log(f'  body: {json.dumps(err_body, ensure_ascii=False)[:300]}')
        except Exception:
            log(f'  raw: {resp.text[:300]}')
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        log(f'  error: {e}')
        return None, str(e)


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
            val = json.dumps(val, ensure_ascii=False)
        print(f"ℹ️  {key}: {val}")


def normalize_host(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def export_hosts(headers, user_id, filter_links=None):
    print()
    print("ℹ️ === GET /user/{user_id}/hosts ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return []

    hosts = data.get("hosts", [])
    total_all = len(hosts)
    log(f'Всего хостов от API: {total_all}')

    if filter_links:
        filter_set = {normalize_host(link) for link in filter_links}
        log(f'Фильтр ({len(filter_set)} доменов): {filter_set}')
        matched = []
        for h in hosts:
            h_norm = normalize_host(h.get("unicode_host_url", ""))
            if h_norm in filter_set:
                log(f'  ✓ {h.get("unicode_host_url", "")} → host_id={h.get("host_id", "")}')
                matched.append(h)
            else:
                pass
        not_found = filter_set - {normalize_host(h.get("unicode_host_url", "")) for h in matched}
        if not_found:
            log(f'  ✗ Не найдены: {not_found}')
        hosts = matched
        print(f"ℹ️  Фильтр: указано {len(filter_links)} сайтов, найдено {len(hosts)} из {total_all}")
    else:
        print(f"ℹ️  Всего сайтов: {total_all}")

    print()

    total = len(hosts)
    rows = []
    for h in hosts[:MAX_ROWS]:
        main_mirror = h.get("main_mirror", {})
        mirror_url = main_mirror.get("unicode_host_url", "-") if main_mirror else "-"
        rows.append([
            h.get("host_id", ""),
            h.get("ascii_host_url", ""),
            h.get("unicode_host_url", ""),
            str(h.get("verified", "")),
            mirror_url
        ])

    print_table(
        ["host_id", "ascii_host_url", "unicode_host_url", "verified", "main_mirror"],
        rows,
        total_count=total
    )

    return hosts[:MAX_ROWS]


def export_host_details(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id} ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    print_kv(data)


def export_summary(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/summary ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/summary", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    print_kv(data)


def export_sitemaps(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/sitemaps ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/sitemaps", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    sitemaps = data.get("sitemaps", [])
    print(f"ℹ️  Всего sitemap: {len(sitemaps)}")
    print()

    rows = []
    for s in sitemaps[:MAX_ROWS]:
        sources = s.get("sources", [])
        sources_str = ", ".join(sources) if sources else "-"
        rows.append([
            s.get("sitemap_id", ""),
            s.get("sitemap_url", ""),
            s.get("last_access_date", ""),
            str(s.get("errors_count", "")),
            str(s.get("urls_count", "")),
            str(s.get("children_count", "")),
            s.get("sitemap_type", ""),
            sources_str
        ])

    print_table(
        ["sitemap_id", "sitemap_url", "last_access_date", "errors_count",
         "urls_count", "children_count", "sitemap_type", "sources"],
        rows,
        total_count=len(sitemaps)
    )


def export_user_sitemaps(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/user-added-sitemaps ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/user-added-sitemaps", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    sitemaps = data.get("sitemaps", [])
    count = data.get("count", len(sitemaps))
    print(f"ℹ️  Добавлено пользователем: {count}")
    print()

    rows = []
    for s in sitemaps[:MAX_ROWS]:
        rows.append([
            s.get("sitemap_id", ""),
            s.get("sitemap_url", ""),
            s.get("added_date", "")
        ])

    print_table(
        ["sitemap_id", "sitemap_url", "added_date"],
        rows,
        total_count=count
    )


def export_verification(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/verification ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/verification", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    print_kv(data)


def export_owners(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/owners ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/owners", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    users = data.get("users", [])
    print(f"ℹ️  Владельцев: {len(users)}")
    print()

    rows = []
    for u in users[:MAX_ROWS]:
        rows.append([
            u.get("user_login", ""),
            u.get("verification_uin", ""),
            u.get("verification_type", ""),
            u.get("verification_date", "")
        ])

    print_table(
        ["user_login", "verification_uin", "verification_type", "verification_date"],
        rows,
        total_count=len(users)
    )


def export_external_links(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/links/external/samples ===")
    print()

    data, err = api_get(
        f"{BASE_URL}/user/{user_id}/hosts/{host_id}/links/external/samples",
        headers, params={"offset": 0, "limit": MAX_ROWS}
    )
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    total = data.get("count", 0)
    links = data.get("links", [])
    print(f"ℹ️  Всего внешних ссылок: {total}")
    print()

    rows = []
    for l in links[:MAX_ROWS]:
        rows.append([
            l.get("source_url", ""),
            l.get("destination_url", ""),
            l.get("discovery_date", ""),
            l.get("source_last_access_date", "")
        ])

    print_table(
        ["source_url", "destination_url", "discovery_date", "source_last_access_date"],
        rows,
        total_count=total
    )


def export_limits(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/pro/limits ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/pro/limits", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    limits = data.get("limits", [])
    print(f"ℹ️  Всего лимитов: {len(limits)}")
    print()

    rows = []
    for l in limits[:MAX_ROWS]:
        rows.append([
            l.get("owner", ""),
            l.get("feature", ""),
            str(l.get("limit", "")),
            str(l.get("used", "")),
            str(l.get("remaining", "")),
            l.get("period_start", ""),
            l.get("period_end", ""),
            str(l.get("is_active", ""))
        ])

    print_table(
        ["owner", "feature", "limit", "used", "remaining", "period_start", "period_end", "is_active"],
        rows,
        total_count=len(limits)
    )


def export_recrawl_quota(headers, user_id, host_id):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/recrawl/quota ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{host_id}/recrawl/quota", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    info = data.get("host_sitemaps_recrawl_limit_info", data)
    print_kv(info)


def export_sqi_history(headers, user_id, host_id, date_from, date_to):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/sqi-history ===")
    print()

    params = {}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    data, err = api_get(
        f"{BASE_URL}/user/{user_id}/hosts/{host_id}/sqi-history",
        headers, params=params if params else None
    )
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    points = data.get("points", [])
    print(f"ℹ️  Записей: {len(points)}")
    print()

    rows = []
    for p in points[:MAX_ROWS]:
        rows.append([p.get("date", ""), str(p.get("value", ""))])

    print_table(["date", "value"], rows, total_count=len(points))


def export_search_events(headers, user_id, host_id, date_from, date_to):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/search-urls/events/history ===")
    print()

    params = {}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    data, err = api_get(
        f"{BASE_URL}/user/{user_id}/hosts/{host_id}/search-urls/events/history",
        headers, params=params if params else None
    )
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    indicators = data.get("indicators", {})
    for event_type, events in indicators.items():
        print(f"ℹ️  Тип: {event_type}")
        if isinstance(events, list):
            rows = []
            for e in events[:MAX_ROWS]:
                rows.append([e.get("date", ""), str(e.get("value", ""))])
            print_table(["date", "value"], rows, total_count=len(events))
        else:
            print_kv(events if isinstance(events, dict) else {"value": events})
        print()


def export_important_urls(headers, user_id, host_id, site_url):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/important-urls/history ===")
    print()

    data, err = api_get(
        f"{BASE_URL}/user/{user_id}/hosts/{host_id}/important-urls/history",
        headers, params={"url": site_url}
    )
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    if "error_code" in data:
        print(f"⚠️  Ошибка API: {data.get('error_code')} — {data.get('error_message', '')}")
        return

    print_kv(data)


def export_broken_links(headers, user_id, host_id, date_from, date_to, indicator=None):
    print()
    print(f"ℹ️ === GET /user/{user_id}/hosts/{host_id}/links/internal/broken/samples ===")
    print()

    params = {"offset": 0, "limit": MAX_ROWS}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    if indicator:
        params["indicator"] = indicator

    data, err = api_get(
        f"{BASE_URL}/user/{user_id}/hosts/{host_id}/links/internal/broken/samples",
        headers, params=params
    )
    if err:
        print(f"⚠️  Ошибка: {err}")
        return

    if isinstance(data, dict) and "links" in data:
        links = data["links"]
        total = data.get("count", len(links))
        print(f"ℹ️  Всего сломанных ссылок: {total}")
        print()
        rows = []
        for l in links[:MAX_ROWS]:
            rows.append([
                l.get("source_url", ""),
                l.get("destination_url", ""),
                l.get("last_access_date", ""),
                l.get("error_code", "")
            ])
        print_table(
            ["source_url", "destination_url", "last_access_date", "error_code"],
            rows,
            total_count=total
        )
    elif isinstance(data, list):
        print(f"ℹ️  Элементов: {len(data)}")
        print()
        for item in data[:MAX_ROWS]:
            print_kv(item)
    else:
        print_kv(data)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ === ЭКСПОРТ ДАННЫХ ЯНДЕКС.ВЕБМАСТЕРА ===")

    config = load_config()
    script_data = load_script_data()

    token = config.get("oauth_token")
    if not token:
        print()
        print("⚠️  Для запуска скрипта не хватает данных: oauth_token")
        print("ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить")
        return

    user_id = config.get("user_id")
    if not user_id:
        print()
        print("⚠️  Для запуска скрипта не хватает данных: user_id")
        print("ℹ️  Получите user_id на вкладке Яндекс → Ключи → Получить")
        return

    date_from = script_data.get("date_from", "")
    date_to = script_data.get("date_to", "")
    query_indicator = script_data.get("query_indicator", "TOTAL_SHOWS")
    broken_indicator = script_data.get("broken_indicator", "")
    site_url = config.get("sitemap_path", "")

    links_raw = script_data.get("links", "")
    if isinstance(links_raw, str):
        filter_links = [l.strip() for l in links_raw.strip().split('\n') if l.strip()] or None
    elif isinstance(links_raw, list):
        filter_links = links_raw if links_raw else None
    else:
        filter_links = None

    log(f'token: {token[:20]}...')
    log(f'user_id: {user_id}')
    log(f'filter_links: {filter_links}')
    log(f'date_from: {date_from}, date_to: {date_to}')
    log(f'query_indicator: {query_indicator}, broken_indicator: {broken_indicator}')

    headers = {"Authorization": f"OAuth {token}"}

    print(f"ℹ️  user_id: {user_id}")
    if filter_links:
        print(f"ℹ️  Сайтов для анализа: {len(filter_links)}")
    if date_from:
        print(f"ℹ️  date_from: {date_from}")
    if date_to:
        print(f"ℹ️  date_to: {date_to}")
    if query_indicator:
        print(f"ℹ️  query_indicator: {query_indicator}")
    if broken_indicator:
        print(f"ℹ️  broken_indicator: {broken_indicator}")

    hosts = export_hosts(headers, user_id, filter_links)

    for host in hosts:
        hid = host.get("host_id", "")
        h_url = host.get("unicode_host_url", hid)
        print()
        print(f"ℹ️ ─────────────────────────────────────────────")
        print(f"ℹ️  Хост: {h_url}")
        print(f"ℹ️ ─────────────────────────────────────────────")

        export_host_details(headers, user_id, hid)
        export_summary(headers, user_id, hid)
        export_sitemaps(headers, user_id, hid)
        export_user_sitemaps(headers, user_id, hid)
        export_verification(headers, user_id, hid)
        export_owners(headers, user_id, hid)
        export_external_links(headers, user_id, hid)
        export_limits(headers, user_id, hid)
        export_recrawl_quota(headers, user_id, hid)

        if date_from or date_to:
            export_sqi_history(headers, user_id, hid, date_from, date_to)
            export_search_events(headers, user_id, hid, date_from, date_to)
            export_broken_links(headers, user_id, hid, date_from, date_to, broken_indicator)
        else:
            print()
            print(f"ℹ️  ⏭️  sqi-history, search-events, broken-links пропущены (не указана дата)")

        if h_url:
            export_important_urls(headers, user_id, hid, h_url)

    print()
    print("ℹ️ === ЭКСПОРТ ЗАВЕРШЁН ===")
    print(f"ℹ️  Всего сайтов: {len(hosts)}")


if __name__ == "__main__":
    main()
