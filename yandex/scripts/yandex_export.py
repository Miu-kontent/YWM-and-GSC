import json
import os
import sys
import time
import requests


BASE_URL = "https://api.webmaster.yandex.net/v4"


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)


def load_script_data():
    array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'yandex_export.json')
    if not os.path.exists(array_path):
        return {}
    try:
        with open(array_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def api_get(url, headers, params=None, retries=5, timeout=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return None, f"Соединение не установлено после {retries} попыток"
            time.sleep(1)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, f"Превышен таймаут ({timeout}с) после {retries} попыток"
            time.sleep(1)
        except Exception as e:
            return None, str(e)


def strip_protocol(url):
    if '://' in url:
        url = url.split('://', 1)[1]
    if url.endswith('/') and url != '/':
        pass
    return url


def make_sitemap_path(full_url, host_unicode):
    path = full_url
    if '://' in path:
        path = path.split('://', 1)[1]
    slash_idx = path.find('/')
    if slash_idx != -1:
        path = path[slash_idx:]
    else:
        path = '/'
    return path


def extract_site_url(host_unicode):
    if '://' in host_unicode:
        return host_unicode.split('://', 1)[1].rstrip('/')
    return host_unicode.rstrip('/')


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

    raw_sitemap = config.get("sitemap_path", "")
    if isinstance(raw_sitemap, list):
        correct_sitemaps = raw_sitemap
    elif raw_sitemap:
        correct_sitemaps = [raw_sitemap]
    else:
        correct_sitemaps = []

    links_raw = script_data.get("links", "")
    if isinstance(links_raw, str):
        filter_links = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        filter_links = links_raw
    else:
        filter_links = []

    headers = {"Authorization": f"OAuth {token}"}

    print(f"ℹ️  user_id: {user_id}")
    if filter_links:
        print(f"ℹ️  Фильтр по ссылкам: {len(filter_links)} шт.")
    if correct_sitemaps:
        print(f"ℹ️  Правильные сайтмапы: {correct_sitemaps}")

    hosts_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts", headers)
    if err:
        print(f"⚠️  Ошибка получения списка сайтов: {err}")
        return

    all_hosts = hosts_data.get("hosts", [])

    mirrors_of = {}
    for h in all_hosts:
        mm = h.get("main_mirror") or {}
        mm_key = mm.get("host_id") or mm.get("unicode_host_url")
        if mm_key:
            mirrors_of.setdefault(mm_key, []).append(extract_site_url(h.get("unicode_host_url", "")))

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
            url = h.get("unicode_host_url", "")
            site = extract_site_url(url)
            if site.lower() in filter_index:
                hosts.append(h)

        hosts.sort(key=lambda h: filter_index.get(extract_site_url(h.get("unicode_host_url", "")).lower(), 0))
    else:
        hosts = all_hosts

    def _is_mirror(h):
        mm = h.get("main_mirror") or {}
        return bool(mm.get("host_id") or mm.get("unicode_host_url"))

    skipped_mirrors = [h for h in hosts if _is_mirror(h)]
    if skipped_mirrors:
        for h in skipped_mirrors:
            mm = h.get("main_mirror") or {}
            print(f"ℹ️  Пропуск (это зеркало): {extract_site_url(h.get('unicode_host_url', ''))} → {extract_site_url(mm.get('unicode_host_url', mm.get('host_url', '')))}")
        hosts = [h for h in hosts if not _is_mirror(h)]

    total = len(hosts)
    print(f"ℹ️  Сайтов к обработке: {total}")
    print()

    export_groups = script_data.get("export_groups", []) or []
    need_status = "status" in export_groups
    need_sitemaps = "sitemaps" in export_groups
    need_problems = "problems" in export_groups
    print(f"ℹ️  Группы: {'Статус' if need_status else ''}{', ' if need_status and (need_sitemaps or need_problems) else ''}{'Сайтмапы' if need_sitemaps else ''}{', ' if need_sitemaps and need_problems else ''}{'Проверки' if need_problems else ''}")

    unverified_count = 0
    not_ok_count = 0
    with_recommendations_count = 0
    with_errors_count = 0
    mirrors_count = 0
    without_correct_sitemap_count = 0
    with_wrong_sitemaps_count = 0
    sitemaps_not_ok_count = 0

    processed = 0
    for host in hosts:
        processed += 1
        hid = host.get("host_id", "")
        h_url = host.get("unicode_host_url", "")
        h_verified = host.get("verified", False)

        site = extract_site_url(h_url)

        if not h_verified:
            unverified_count += 1

        verified_str = "✓" if h_verified else "✗"

        own_main = host.get("main_mirror") or {}
        if own_main.get("unicode_host_url"):
            mirror_cell = [f"→ {extract_site_url(own_main['unicode_host_url'])}"]
        else:
            mirror_cell = mirrors_of.get(hid, ["-"])
        if own_main.get("unicode_host_url") or mirrors_of.get(hid):
            mirrors_count += 1

        cells = [site, verified_str]

        data_status = "-"
        if need_status:
            if h_verified:
                details, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}", headers)
                data_status = "-"
                if err:
                    print(f"⚠️  Ошибка получения статуса сайта {hid}: {err}")
                    data_status = "NONE"
                else:
                    data_status = details.get("host_data_status", "-")
                    if data_status != "OK":
                        not_ok_count += 1
            else:
                data_status = "—"
            cells.append(data_status)

        cells.append(mirror_cell)

        sitemaps_cell = "NONE"
        if need_sitemaps:
            if h_verified:
                sitemaps_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}/sitemaps", headers)
                sitemaps_list = []
                sitemap_ids_in_api = set()
                if err:
                    print(f"⚠️  Ошибка получения сайтмапов {hid}: {err}")
                    sitemaps_cell = "NONE"
                else:
                    for s in sitemaps_data.get("sitemaps", []):
                        sitemap_ids_in_api.add(s.get("sitemap_id", ""))
                        sitemaps_list.append({
                            "url": s.get("sitemap_url", ""),
                            "path": make_sitemap_path(s.get("sitemap_url", ""), h_url),
                            "errors_count": s.get("errors_count", 0),
                            "sitemap_id": s.get("sitemap_id", "")
                        })

                    user_sitemaps_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}/user-added-sitemaps", headers)
                    pending_sitemaps = []
                    if err:
                        print(f"⚠️  Ошибка получения добавленных сайтмапов {hid}: {err}")
                        sitemaps_cell = "NONE"
                    else:
                        for us in user_sitemaps_data.get("sitemaps", []):
                            us_id = us.get("sitemap_id", "")
                            us_url = us.get("sitemap_url", "")
                            if us_id not in sitemap_ids_in_api:
                                pending_sitemaps.append({
                                    "url": us_url,
                                    "path": make_sitemap_path(us_url, h_url),
                                    "errors_count": 0,
                                    "sitemap_id": us_id,
                                    "pending": True
                                })

                        all_sitemaps = sitemaps_list + pending_sitemaps

                        has_correct = False
                        for s in all_sitemaps:
                            if s["path"] in correct_sitemaps:
                                has_correct = True
                                break
                        if not has_correct and correct_sitemaps:
                            without_correct_sitemap_count += 1

                        has_wrong = False
                        for s in all_sitemaps:
                            if s["path"] not in correct_sitemaps:
                                has_wrong = True
                                break
                        if has_wrong:
                            with_wrong_sitemaps_count += 1

                        has_sitemap_not_ok = any(
                            not s.get("pending") and s["errors_count"] > 0 for s in all_sitemaps
                        )
                        if has_sitemap_not_ok:
                            sitemaps_not_ok_count += 1

                        sitemap_cells = []
                        status_cells = []
                        for s in all_sitemaps:
                            sitemap_cells.append(s["path"])
                            if s.get("pending"):
                                status_cells.append("В обработке")
                            elif s["errors_count"] == 0:
                                status_cells.append("OK")
                            else:
                                status_cells.append("ERROR")

                        sitemaps_display = sitemap_cells if sitemap_cells else ["-"]
                        statuses_display = status_cells if status_cells else ["-"]
                        sitemaps_cell = [{"path": p, "status": st} for p, st in zip(sitemaps_display, statuses_display)]

            else:
                sitemaps_cell = "—"
            cells.append(sitemaps_cell)

        rec_cell = "NONE"
        err_cell = "NONE"
        if need_problems:
            if h_verified:
                summary_data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts/{hid}/summary", headers)
                if err:
                    print(f"⚠️  Ошибка получения проверок {hid}: {err}")
                else:
                    site_problems = summary_data.get("site_problems", {})
                    recommendations = site_problems.get("POSSIBLE_PROBLEM", 0) + site_problems.get("RECOMMENDATION", 0)
                    errors = site_problems.get("CRITICAL", 0) + site_problems.get("FATAL", 0)

                    if recommendations > 0:
                        with_recommendations_count += 1
                    if errors > 0:
                        with_errors_count += 1

                    rec_cell = recommendations
                    err_cell = errors
            else:
                rec_cell = "—"
                err_cell = "—"

            cells += [rec_cell, err_cell]

        print(f"__TABLE_ROW__:{json.dumps({'cells': cells}, ensure_ascii=False)}")
        print(f"ℹ️  Обработка сайтов - {processed}/{total} ({round(processed / total * 100)}%)")

    summary_data = {
        "Всего сайтов": total,
        "Не подтверждено": unverified_count,
        "С зеркалами": mirrors_count,
    }
    if need_status:
        summary_data["Не OK (host_data_status)"] = not_ok_count
    if need_problems:
        summary_data["С рекомендациями"] = with_recommendations_count
        summary_data["С ошибками"] = with_errors_count
    if need_sitemaps:
        summary_data["Без правильного сайтмапа"] = without_correct_sitemap_count
        summary_data["С неправильными сайтмапами"] = with_wrong_sitemaps_count
        summary_data["Сайтмапы не в OK"] = sitemaps_not_ok_count

    print()
    print(f"__SUMMARY__:{json.dumps(summary_data, ensure_ascii=False)}")
    print("__TABLE_DONE__:{}")

    print()
    print("ℹ️ === ЭКСПОРТ ЗАВЕРШЁН ===")


if __name__ == "__main__":
    main()
