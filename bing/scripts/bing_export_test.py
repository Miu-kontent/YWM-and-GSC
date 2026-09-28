"""
bing_export_test.py — тестовая выгрузка данных Bing Webmaster API (только чтение).

Прогоняет все read-only методы справочника IWebmasterApi и печатает результат
в лог-блок (как yandex_export_test.py / gsc_export_test.py) — без табличного
протокола __TABLE_ROW__. Смысл прогона — посмотреть, какие данные и в каком
виде отдаёт Bing, до написания основной выгрузки.

Вход (../arrays/bing_export_test.json):
    links    — сайт(ы) для проверки; пусто → первые 3 сайта из GetUserSites
    urls     — URL(ы) уровня страницы; пусто → корень каждого сайта
    keyword  — глобальный блок GetKeyword*/GetRelatedKeywords; пусто → пропуск

Требования: bing/config.json → active_account, bing/accounts.json → токены.
Токен обновляется автоматически (см. bing_client.get_access_token).
"""
import json
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bing_client as bc

SCRIPT_NAME = "bing_export_test"
KEYWORD_DAYS = 7
CRAWL_STATS_TAIL = 3
TRAFFIC_TAIL = 7
ROW_LIMIT = 10
SITES_LIMIT = 10
ROLES_LIMIT = 20
DATE_FIELDS = ("Date", "Submitted", "LastCrawled", "CrawlDate", "DiscoveryDate", "LastCrawledDate")

stats = {"requests": 0, "errors": 0, "blocks_failed": 0}


# ======================== ВЫВОД ========================

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


def section(title):
    print()
    print(f"── {title} " + "─" * max(0, 60 - len(title)))


def field(value):
    return "—" if value in (None, "", [], {}) else str(value)


def table(headers, rows, limit=None):
    if limit:
        rows = rows[:limit]
    if not rows:
        print("   — данных нет")
        return
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    sep = "   " + "  ".join("─" * w for w in widths)
    print(sep)
    print("   " + "  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)).rstrip())
    print(sep)
    for row in rows:
        print("   " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)).rstrip())


def kv(label, value):
    print(f"   {label}: {field(value)}")


def as_list(data):
    if isinstance(data, list):
        return [item for item in data if item is not None]
    if isinstance(data, dict):
        return [data]
    return []


def dated(item):
    """Читаемые даты из объекта Bing."""
    if not isinstance(item, dict):
        return str(item)
    return " | ".join(f"{key}={bc.ms_date(item[key])}" for key in DATE_FIELDS if item.get(key))


# ======================== ВЫЗОВЫ ========================

def call(method, params=None, body=None):
    ok, data, error = bc.call(method, params=params, body=body)
    stats["requests"] += 1
    if not ok:
        stats["errors"] += 1
    return ok, data, error


def failed(method, error):
    print(f"   ⚠️ {method}: {error}")


def safe_block(title, func, *args):
    """Исключение внутри блока не должно ронять весь прогон — ловим и идём дальше."""
    try:
        func(*args)
    except Exception as e:
        stats["blocks_failed"] += 1
        bc.dbg("BLOCK", "блок упал", block=title, error_type=type(e).__name__, detail=str(e))
        print(f"   ⚠️ Блок «{title}» прерван: {type(e).__name__}: {e}")


# ======================== БЛОКИ ========================

def block_sites(site, urls):
    section("1. Сайты, права и настройки")
    ok, data, error = call("GetSiteRoles", {"siteUrl": site, "includeAllSubdomains": "true"})
    if ok:
        roles = as_list(data)
        rows = []
        for role in roles:
            rows.append((
                field(role.get("Email")),
                bc.role_label(role.get("Role")),
                field(role.get("Site")),
                field(role.get("VerificationSite")),
                "expired" if role.get("Expired") else "активна",
            ))
        table(["Email", "Роль", "Сайт", "Верификация", "Состояние"], rows, limit=ROLES_LIMIT)
        if len(rows) > ROLES_LIMIT:
            print(f"   ℹ️ показаны первые {ROLES_LIMIT} из {len(rows)} ролей "
                  f"(includeAllSubdomains=true отдаёт роли по всем поддоменам)")
    else:
        failed("GetSiteRoles", error)

    ok, data, error = call("GetConnectedPages", {"siteUrl": site})
    if ok:
        table(["Master", "Connected"],
              [(field(p.get("MasterUrl") or p.get("Url")), field(p.get("ConnectedUrl") or p.get("Site")))
               for p in as_list(data)])
    else:
        failed("GetConnectedPages", error)

    ok, data, error = call("GetCountryRegionSettings", {"siteUrl": site})
    if ok:
        table(["Страна", "Тип", "Дата"],
              [(field(r.get("TwoLetterIsoCountryCode")), field(r.get("Type")),
                bc.ms_date(r.get("Date"))) for r in as_list(data)])
    else:
        failed("GetCountryRegionSettings", error)

    ok, data, error = call("GetSiteMoves", {"siteUrl": site})
    if ok:
        table(["Источник", "Цель", "MoveType", "MoveScope"],
              [(field(m.get("SourceUrl")), field(m.get("TargetUrl")), field(m.get("MoveType")),
                field(m.get("MoveScope"))) for m in as_list(data)])
    else:
        failed("GetSiteMoves", error)


def block_feeds(site):
    section("2. Фиды и сайтмапы")
    ok, data, error = call("GetFeeds", {"siteUrl": site})
    feeds = as_list(data) if ok else []
    if ok:
        table(["Url", "Статус", "Тип", "URL в фиде", "Размер", "Подано"],
              [(field(f.get("Url")), field(f.get("Status")), field(f.get("Type")),
                field(f.get("UrlCount")), field(f.get("FileSize")), bc.ms_date(f.get("Submitted")))
               for f in feeds])
    else:
        failed("GetFeeds", error)

    first_url = next((f.get("Url") for f in feeds if f.get("Url")), "")
    if not first_url:
        print("   ℹ️ GetFeedDetails пропущен — нет фидов")
        return
    ok, data, error = call("GetFeedDetails", {"siteUrl": site, "feedUrl": first_url})
    if ok:
        print(f"   Детали фида {first_url}:")
        for f in as_list(data):
            kv("  Status", f.get("Status"))
            kv("  UrlCount", f.get("UrlCount"))
            kv("  FileSize", f.get("FileSize"))
            kv("  Compressed", f.get("Compressed"))
            kv("  LastCrawled", bc.ms_date(f.get("LastCrawled")))
    else:
        failed("GetFeedDetails", error)


def block_crawl(site):
    section("3. Краулинг")
    ok, data, error = call("GetCrawlStats", {"siteUrl": site})
    if ok:
        items = as_list(data)
        table(["Дата", "Обойдено", "В индексе", "Ошибки", "2xx", "301", "302", "4xx", "5xx"],
              [(bc.ms_date(s.get("Date")), field(s.get("CrawledPages")), field(s.get("InIndex")),
                field(s.get("CrawlErrors")), field(s.get("Code2xx")), field(s.get("Code301")),
                field(s.get("Code302")), field(s.get("Code4xx")), field(s.get("Code5xx")))
               for s in items[-CRAWL_STATS_TAIL:]])
        if len(items) > CRAWL_STATS_TAIL:
            print(f"   ℹ️ показаны последние {CRAWL_STATS_TAIL} из {len(items)} записей")
        kv("ContainsMalware (нет longer)", field(as_list(data)[-1].get("ContainsMalware")) if items else "—")
    else:
        failed("GetCrawlStats", error)

    ok, data, error = call("GetCrawlIssues", {"siteUrl": site})
    if ok:
        table(["URL", "Проблемы", "Входящих ссылок", "HTTP"],
              [(field(i.get("Url")), bc.crawl_issue_labels(i.get("Issues")),
                field(i.get("InLinks")), field(i.get("HttpCode"))) for i in as_list(data)],
              limit=ROW_LIMIT)
    else:
        failed("GetCrawlIssues", error)

    ok, data, error = call("GetCrawlSettings", {"siteUrl": site})
    if ok:
        settings = data if isinstance(data, dict) else {}
        kv("AjaxEnabled", settings.get("AjaxEnabled"))
        kv("CrawlBoostEnabled", settings.get("CrawlBoostEnabled"))
        kv("CrawlBoostAvailable", settings.get("CrawlBoostAvailable"))
        rate = settings.get("CrawlRate")
        kv("CrawlRate", f"{len(rate)} значений (по часам)" if isinstance(rate, list) else rate)
    else:
        failed("GetCrawlSettings", error)

    ok, data, error = call("GetFetchedUrls", {"siteUrl": site})
    if ok:
        items = as_list(data)
        table(["URL", "Обойден", "Истёк", "Дата"],
              [(field(f.get("Url")), field(f.get("Fetched")), field(f.get("Expired")),
                bc.ms_date(f.get("Date"))) for f in items], limit=ROW_LIMIT)
        if len(items) > ROW_LIMIT:
            print(f"   ℹ️ показаны первые {ROW_LIMIT} из {len(items)}")
    else:
        failed("GetFetchedUrls", error)


def block_quotas(site):
    section("4. Квоты на отправку")
    ok, data, error = call("GetUrlSubmissionQuota", {"siteUrl": site})
    if ok:
        quota = data if isinstance(data, dict) else {}
        kv("Дневная квота URL", quota.get("DailyQuota"))
        kv("Месячная квота URL", quota.get("MonthlyQuota"))
    else:
        failed("GetUrlSubmissionQuota", error)

    ok, data, error = call("GetContentSubmissionQuota", {"siteUrl": site})
    if ok:
        quota = data if isinstance(data, dict) else {}
        kv("Дневная квота контента", quota.get("DailyQuota"))
        kv("Месячная квота контента", quota.get("MonthlyQuota"))
    else:
        failed("GetContentSubmissionQuota", error)


def block_blocks(site):
    section("5. Блокировки, deep links и параметры URL")
    ok, data, error = call("GetBlockedUrls", {"siteUrl": site})
    if ok:
        table(["URL", "Тип", "Запрос", "Дней до конца", "Дата"],
              [(field(b.get("Url")), field(b.get("EntityType")), field(b.get("RequestType")),
                field(b.get("DaysToExpire")), bc.ms_date(b.get("Date"))) for b in as_list(data)],
              limit=ROW_LIMIT)
    else:
        failed("GetBlockedUrls", error)

    ok, data, error = call("GetActivePagePreviewBlocks", {"siteUrl": site})
    if ok:
        table(["URL", "Причина", "Дата"],
              [(field(p.get("Url")), field(p.get("Reason")), bc.ms_date(p.get("Date")))
               for p in as_list(data)], limit=ROW_LIMIT)
    else:
        failed("GetActivePagePreviewBlocks", error)

    ok, data, error = call("GetDeepLinkBlocks", {"siteUrl": site})
    if ok:
        table(["Рынок", "URL поиска", "URL deep link", "Вес"],
              [(field(d.get("Market")), field(d.get("SearchUrl")), field(d.get("DeepLinkUrl")),
                field(d.get("Weight"))) for d in as_list(data)], limit=ROW_LIMIT)
    else:
        failed("GetDeepLinkBlocks", error)

    ok, data, error = call("GetQueryParameters", {"siteUrl": site})
    if ok:
        table(["Параметр", "Включён", "Источник", "Дата"],
              [(field(p.get("Parameter")), field(p.get("IsEnabled")), field(p.get("Source")),
                bc.ms_date(p.get("Date"))) for p in as_list(data)])
    else:
        failed("GetQueryParameters", error)


def block_traffic(site):
    section("6. Трафик (ежедневные и еженедельные данные)")
    ok, data, error = call("GetRankAndTrafficStats", {"siteUrl": site})
    if ok:
        items = as_list(data)
        table(["Дата", "Клики", "Показы"],
              [(bc.ms_date(t.get("Date")), field(t.get("Clicks")), field(t.get("Impressions")))
               for t in items[-TRAFFIC_TAIL:]])
        if len(items) > TRAFFIC_TAIL:
            print(f"   ℹ️ показаны последние {TRAFFIC_TAIL} из {len(items)} записей (ежедневно)")
    else:
        failed("GetRankAndTrafficStats", error)

    ok, data, error = call("GetQueryStats", {"siteUrl": site})
    if ok:
        items = as_list(data)
        table(["Запрос", "Клики", "Показы", "Позиция клика", "Позиция показа", "Дата"],
              [(field(q.get("Query")), field(q.get("Clicks")), field(q.get("Impressions")),
                field(q.get("AvgClickPosition")), field(q.get("AvgImpressionPosition")),
                bc.ms_date(q.get("Date"))) for q in items], limit=ROW_LIMIT)
        if len(items) > ROW_LIMIT:
            print(f"   ℹ️ показаны первые {ROW_LIMIT} из {len(items)} (данные за неделю)")
    else:
        failed("GetQueryStats", error)

    ok, data, error = call("GetPageStats", {"siteUrl": site})
    if ok:
        items = as_list(data)
        table(["Страница", "Клики", "Показы", "Позиция клика", "Позиция показа", "Дата"],
              [(field(p.get("Page") or p.get("Query")), field(p.get("Clicks")),
                field(p.get("Impressions")), field(p.get("AvgClickPosition")),
                field(p.get("AvgImpressionPosition")), bc.ms_date(p.get("Date"))) for p in items],
              limit=ROW_LIMIT)
    else:
        failed("GetPageStats", error)


def block_url(site, url):
    section(f"7. Данные по URL: {url}")
    ok, data, error = call("GetUrlInfo", {"siteUrl": site, "url": url})
    if ok:
        info = data if isinstance(data, dict) else {}
        kv("Url", info.get("Url"))
        kv("HTTP-статус", info.get("HttpStatus"))
        kv("Размер документа", info.get("DocumentSize"))
        kv("Анкоров", info.get("AnchorCount"))
        kv("Дочерних URL", info.get("TotalChildUrlCount"))
        kv("Это страница", info.get("IsPage"))
        kv("Обнаружен", bc.ms_date(info.get("DiscoveryDate")))
        kv("Последний обход", bc.ms_date(info.get("LastCrawledDate")))
    else:
        failed("GetUrlInfo", error)

    ok, data, error = call("GetUrlTrafficInfo", {"siteUrl": site, "url": url})
    if ok:
        info = data if isinstance(data, dict) else {}
        kv("URL трафика", info.get("Url"))
        kv("Клики", info.get("Clicks"))
        kv("Показы", info.get("Impressions"))
        kv("Это страница", info.get("IsPage"))
    else:
        failed("GetUrlTrafficInfo", error)

    # Только чтение, но по факту Bing отвечает 405 на POST — шлём GET.
    # Полное тело (Document/Headers) не печатаем — только сводку.
    ok, data, error = call("GetFetchedUrlDetails", {"siteUrl": site, "url": url})
    if ok:
        info = data if isinstance(data, dict) else {}
        kv("URL", info.get("Url"))
        kv("Статус", info.get("Status"))
        kv("Дата", bc.ms_date(info.get("Date")))
        document = info.get("Document") or ""
        kv("Длина документа", len(document) if isinstance(document, str) else field(document))
    else:
        failed("GetFetchedUrlDetails", error)

    filter_properties = {
        "__type": "FilterProperties:#Microsoft.Bing.Webmaster.Api",
        "CrawlDateFilter": 0, "DiscoveredDateFilter": 0,
        "DocFlagsFilters": 0, "HttpCodeFilters": 0,
    }
    ok, data, error = call("GetChildrenUrlInfo", body={"siteUrl": site, "url": url, "page": 0,
                                                       "filterProperties": filter_properties})
    if ok:
        items = as_list(data)
        table(["URL", "HTTP", "Размер", "Анкоров", "Обход", "Обнаружен"],
              [(field(i.get("Url")), field(i.get("HttpStatus")), field(i.get("DocumentSize")),
                field(i.get("AnchorCount")), bc.ms_date(i.get("LastCrawledDate")),
                bc.ms_date(i.get("DiscoveryDate"))) for i in items], limit=5)
        if len(items) > 5:
            print(f"   ℹ️ показаны первые 5 из {len(items)} (page=0)")
    else:
        failed("GetChildrenUrlInfo", error)

    ok, data, error = call("GetLinkCounts", {"siteUrl": site, "page": 0})
    if ok:
        counts = data if isinstance(data, dict) else {}
        kv("Всего ссылок", counts.get("TotalPages"))
        table(["URL", "Ссылок"],
              [(field(l.get("Url")), field(l.get("Count"))) for l in as_list(counts.get("Links"))],
              limit=5)
    else:
        failed("GetLinkCounts", error)


def block_keywords(keyword):
    section("8. Ключевики (глобальные методы)")
    end = date.today()
    start = end - timedelta(days=KEYWORD_DAYS)
    print(f"   Период: {start.isoformat()} — {end.isoformat()}")
    # country/language не шлём: Bing отвечает 400 InvalidParameter на любое их значение
    # (проверено на RU / ru / ru-RU). Даты ISO обязательны — без них
    # GetRelatedKeywords возвращает пустой список.
    base = {"q": keyword}

    ok, data, error = call("GetKeyword", params={**base, "startDate": start.isoformat(),
                                                  "endDate": end.isoformat()})
    if ok:
        item = data if isinstance(data, dict) else (as_list(data)[0] if as_list(data) else {})
        kv("Запрос", item.get("Query"))
        kv("Показы", item.get("Impressions"))
        kv("Broad-показы", item.get("BroadImpressions"))
    else:
        failed("GetKeyword", error)

    ok, data, error = call("GetKeywordStats", params=base)
    if ok:
        table(["Запрос", "Показы", "Broad-показы", "Дата"],
              [(field(k.get("Query")), field(k.get("Impressions")), field(k.get("BroadImpressions")),
                bc.ms_date(k.get("Date"))) for k in as_list(data)], limit=ROW_LIMIT)
    else:
        failed("GetKeywordStats", error)

    ok, data, error = call("GetRelatedKeywords", params={**base, "startDate": start.isoformat(),
                                                          "endDate": end.isoformat()})
    if ok:
        table(["Похожий запрос", "Показы", "Broad-показы"],
              [(field(k.get("Query")), field(k.get("Impressions")), field(k.get("BroadImpressions")))
               for k in as_list(data)], limit=ROW_LIMIT)
    else:
        failed("GetRelatedKeywords", error)


# ======================== MAIN ========================

def pick_sites(all_sites, links):
    """Пустой links → первые 3 сайта. Иначе — только перечисленные (по хосту)."""
    if not links:
        return all_sites[:3], True
    wanted = {bc.host_of(item) for item in links if bc.host_of(item)}
    return [s for s in all_sites if bc.host_of(s.get("Url")) in wanted], False


def main():
    data = script_data()
    links = lines_of(data.get("links"))
    urls = lines_of(data.get("urls"))
    keyword = (data.get("keyword") or "").strip()

    print("═" * 72)
    print("BING WEBMASTER — ТЕСТОВАЯ ВЫГРУЗКА ДАННЫХ (только чтение)")
    print("═" * 72)

    token, email = bc.get_access_token()
    if not token:
        print(f"❌ {email}")
        return
    bc.set_token(token)
    print(f"👤 Аккаунт: {email}")
    print(f"🔗 Хост API: {bc.API_HOSTS[0]} (fallback {bc.API_HOSTS[1]})")

    section("0. Список сайтов (GetUserSites)")
    ok, data_sites, error = call("GetUserSites")
    if not ok:
        print(f"❌ Не удалось получить список сайтов: {error}")
        return
    all_sites = as_list(data_sites)
    table(["Url", "Верифицирован", "Код файла", "Код DNS"],
          [(field(s.get("Url")), field(s.get("IsVerified")),
            "есть" if s.get("AuthenticationCode") else "—",
            "есть" if s.get("DnsVerificationCode") else "—") for s in all_sites],
          limit=SITES_LIMIT)
    print(f"   Всего сайтов в аккаунте: {len(all_sites)}")
    if len(all_sites) > SITES_LIMIT:
        print(f"   ℹ️ показаны первые {SITES_LIMIT} сайтов")

    sites, auto = pick_sites(all_sites, links)
    if auto:
        print(f"   ℹ️ Поле «Сайты» пустое — обрабатываю первые {len(sites)} сайта(ов)")
    else:
        print(f"   ℹ️ Из списка выбрано сайтов: {len(sites)} из {len(all_sites)}")
    if not sites:
        print("❌ Нет сайтов для обработки")
        return

    for index, site in enumerate(sites, 1):
        site_url = (site.get("Url") or "").strip()
        print()
        print("═" * 72)
        print(f"САЙТ {index}/{len(sites)}: {site_url}")
        print("═" * 72)
        site_urls = urls or [bc.site_root(site_url)]
        safe_block("права и настройки", block_sites, site_url, site_urls)
        safe_block("фиды и сайтмапы", block_feeds, site_url)
        safe_block("краулинг", block_crawl, site_url)
        safe_block("квоты", block_quotas, site_url)
        safe_block("блокировки и параметры", block_blocks, site_url)
        safe_block("трафик", block_traffic, site_url)
        for url in site_urls:
            safe_block(f"данные по URL {url}", block_url, site_url, url)
        print(f"ℹ️ Обработка сайтов - {index}/{len(sites)} ({round(index / len(sites) * 100)}%)")

    if keyword:
        safe_block("ключевики", block_keywords, keyword)
    else:
        print()
        print("── 8. Ключевики " + "─" * 48)
        print("   ℹ️ Поле «Ключевик» пустое — глобальные методы GetKeyword* пропущены")

    print()
    print("═" * 72)
    print("ИТОГО")
    print("═" * 72)
    kv("Сайтов обработано", len(sites))
    kv("Запросов к API", stats["requests"])
    kv("Ошибок API", stats["errors"])
    kv("Блоков прервано", stats["blocks_failed"])
    kv("Время", f"{round(time.time() - STARTED, 1)} сек.")


STARTED = time.time()

if __name__ == "__main__":
    main()
