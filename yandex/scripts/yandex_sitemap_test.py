import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from yandex_checklist import PROBLEM_TYPES

BASE_URL = "https://api.webmaster.yandex.net/v4"
MAX_WORKERS = 6
REQUEST_TIMEOUT = 15
RETRY_SLEEP = 0.5
RETRY_CODES = (429, 500, 502, 503, 504)


from yandex_client import load_config


def load_script_data():
    array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'yandex_sitemap_test.json')
    if not os.path.exists(array_path):
        return {}
    try:
        with open(array_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def api_get(url, headers, params=None):
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json(), None
            if resp.status_code in RETRY_CODES and attempt < 2:
                time.sleep(RETRY_SLEEP)
                continue
            return None, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            if attempt < 2:
                time.sleep(RETRY_SLEEP)
                continue
            return None, f"Таймаут ({REQUEST_TIMEOUT}с)"
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                time.sleep(RETRY_SLEEP)
                continue
            return None, "Соединение не установлено"
        except Exception as e:
            return None, str(e)


def extract_site_url(host_unicode):
    if '://' in host_unicode:
        return host_unicode.split('://', 1)[1].rstrip('/')
    return host_unicode.rstrip('/')


def build_sitemap_data(user_id, hid, headers):
    """Возвращает (urls, statuses, errors, pages) — списки параллельны. При ошибке — (None, None, None, None, err)."""
    sitemaps_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}/sitemaps", headers)
    if err:
        return None, None, None, None, f"сайтмапы: {err}"

    sitemaps_list = []
    sitemap_ids = set()
    for s in sitemaps_data.get("sitemaps", []):
        sid = s.get("sitemap_id", "")
        sitemap_ids.add(sid)
        sitemaps_list.append({
            "url": s.get("sitemap_url", ""),
            "errors_count": s.get("errors_count", 0),
            "urls_count": s.get("urls_count"),
        })

    user_sitemaps_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}/user-added-sitemaps", headers)
    if err:
        return None, None, None, None, f"добавленные сайтмапы: {err}"

    pending_sitemaps = []
    for us in user_sitemaps_data.get("sitemaps", []):
        us_id = us.get("sitemap_id", "")
        if us_id not in sitemap_ids:
            pending_sitemaps.append({
                "url": us.get("sitemap_url", ""),
                "errors_count": 0,
                "urls_count": None,
                "pending": True,
            })

    all_sitemaps = sitemaps_list + pending_sitemaps

    urls = []
    statuses = []
    errors = []
    pages = []
    for s in all_sitemaps:
        urls.append(s["url"])
        if s.get("pending"):
            statuses.append("В обработке")
        elif s["errors_count"] == 0:
            statuses.append("OK")
        else:
            statuses.append("ERROR")
        errors.append(s["errors_count"] if not s.get("pending") else "-")
        pages.append(s["urls_count"] if s["urls_count"] is not None and not s.get("pending") else "-")

    if not all_sitemaps:
        urls, statuses, errors, pages = ["-"], ["-"], ["-"], ["-"]

    return urls, statuses, errors, pages, None


def build_problems(user_id, hid, headers):
    """Возвращает (present_sorted, err) — названия PRESENT-проблем в формате «Название (код)»."""
    problems_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}/diagnostics", headers)
    if err:
        return [], err

    problems = problems_data.get("problems", {}) if isinstance(problems_data, dict) else {}
    present = []
    for code, pr in problems.items():
        if (pr or {}).get("state") == "PRESENT":
            name = (PROBLEM_TYPES.get(code) or {}).get("name")
            present.append(f"{name} ({code})" if name else code)
    return present, None


def process_site(user_id, headers, host):
    """Обрабатывает один сайт. Возвращает (cells, stats)."""
    hid = host.get("host_id", "")
    site = extract_site_url(host.get("unicode_host_url", ""))
    stats = {"sitemaps": 0, "problems": 0, "err_sitemaps": False, "fail": False}

    try:
        urls, statuses, errors, pages, err = build_sitemap_data(user_id, hid, headers)
        if err:
            stats["fail"] = True
            return [site, ["-"], ["-"], ["-"], ["-"], [f"⚠️ {err}"]], stats

        stats["sitemaps"] += len(urls)
        if "ERROR" in statuses:
            stats["err_sitemaps"] = True

        problems, perr = build_problems(user_id, hid, headers)
        if perr:
            stats["fail"] = True
            problems = [f"⚠️ диагностика: {perr}"]
        else:
            stats["problems"] += len(problems)

        if not problems:
            problems = ["-"]

        return [site, urls, statuses, errors, pages, problems], stats
    except Exception as e:
        stats["fail"] = True
        return [site, ["-"], ["-"], ["-"], ["-"], [f"⚠️ {e}"]], stats


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ Запуск: тестовая проверка сайтмапов...")

    config = load_config()
    script_data = load_script_data()

    token = config.get("oauth_token")
    if not token:
        print("⚠️  Для запуска скрипта не хватает данных: oauth_token")
        return

    user_id = config.get("user_id")
    if not user_id:
        print("⚠️  Для запуска скрипта не хватает данных: user_id")
        return

    links_raw = script_data.get("links", "")
    if isinstance(links_raw, str):
        filter_links = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        filter_links = list(links_raw)
    else:
        filter_links = []

    headers = {"Authorization": f"OAuth {token}"}

    if filter_links:
        print(f"ℹ️  Фильтр по ссылкам: {len(filter_links)} шт.")

    hosts_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts", headers)
    if err:
        print(f"⚠️  Ошибка получения списка сайтов: {err}")
        return

    all_hosts = hosts_data.get("hosts", [])

    if filter_links:
        filter_index = {}
        for link in filter_links:
            link = link.strip()
            if '://' in link:
                link = link.split('://', 1)[1]
            link = link.rstrip('/').lower()
            if link not in filter_index:
                filter_index[link] = len(filter_index)

        hosts = []
        for h in all_hosts:
            site = extract_site_url(h.get("unicode_host_url", "")).lower()
            if site in filter_index:
                hosts.append(h)

        hosts.sort(key=lambda h: filter_index.get(extract_site_url(h.get("unicode_host_url", "")).lower(), 0))
    else:
        hosts = list(all_hosts)

    skipped_mirrors = [h for h in hosts if h.get("main_mirror")]
    if skipped_mirrors:
        for h in skipped_mirrors:
            mm = h.get("main_mirror") or {}
            print(f"ℹ️  Пропуск (зеркало): {extract_site_url(h.get('unicode_host_url', ''))} → {extract_site_url(mm.get('unicode_host_url', mm.get('host_url', '')))}")
        hosts = [h for h in hosts if not h.get("main_mirror")]

    unverified = [h for h in hosts if not h.get("verified")]
    if unverified:
        for h in unverified:
            print(f"ℹ️  Пропуск (не подтверждён): {extract_site_url(h.get('unicode_host_url', ''))}")
        hosts = [h for h in hosts if h.get("verified")]

    total = len(hosts)
    print(f"ℹ️  Сайтов к обработке: {total}")
    print(f"ℹ️  Распараллеливание: потоков x{MAX_WORKERS} (по 3 запроса на сайт)")

    sitemaps_total = 0
    problems_total = 0
    sites_with_err_sitemaps = 0
    fail_count = 0
    processed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for cells, stats in executor.map(lambda h: process_site(user_id, headers, h), hosts):
            processed += 1
            sitemaps_total += stats["sitemaps"]
            problems_total += stats["problems"]
            if stats["err_sitemaps"]:
                sites_with_err_sitemaps += 1
            if stats["fail"]:
                fail_count += 1

            print(f"__TABLE_ROW__:{json.dumps({'cells': cells}, ensure_ascii=False)}")
            print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

    summary_data = {
        "Сайтов": total,
        "Сайтмапов": sitemaps_total,
        "Проблем (PRESENT)": problems_total,
        "Сайтов с ошибками сайтмапов": sites_with_err_sitemaps,
        "Ошибок запросов": fail_count,
    }
    print(f"__SUMMARY__:{json.dumps(summary_data, ensure_ascii=False)}")
    print("__TABLE_DONE__:{}")

    print("ℹ️ Готово")


if __name__ == "__main__":
    main()