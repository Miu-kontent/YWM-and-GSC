import json
import os
import sys
import requests


BASE_URL = "https://api.webmaster.yandex.net/v4"
MAX_ROWS = 10


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)


def api_get(url, headers):
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
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


def export_hosts(headers, user_id):
    print()
    print("ℹ️ === GET /user/{user_id}/hosts ===")
    print()

    data, err = api_get(f"{BASE_URL}/user/{user_id}/hosts", headers)
    if err:
        print(f"⚠️  Ошибка: {err}")
        return []

    hosts = data.get("hosts", [])
    total = len(hosts)
    print(f"ℹ️  Всего сайтов: {total}")
    print()

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
    for s in sitemaps:
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
    for s in sitemaps:
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
    for u in users:
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


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ === ЭКСПОРТ ДАННЫХ ЯНДЕКС.ВЕБМАСТЕРА ===")

    config = load_config()

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

    headers = {"Authorization": f"OAuth {token}"}

    print(f"ℹ️  user_id: {user_id}")

    hosts = export_hosts(headers, user_id)

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

    print()
    print("ℹ️ === ЭКСПОРТ ЗАВЕРШЁН ===")
    print(f"ℹ️  Всего сайтов: {len(hosts)}")


if __name__ == "__main__":
    main()
