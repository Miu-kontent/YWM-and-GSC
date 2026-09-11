import json
import os
import sys
import requests


BASE_URL = "https://api-metrika.yandex.net"
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


def get_login(headers):
    try:
        resp = requests.get("https://login.yandex.ru/info", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("login", ""), None
        return None, f"HTTP {resp.status_code}"
    except Exception as e:
        return None, str(e)


def api_get(url, headers, params=None):
    try:
        log(f'GET {url}')
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        log(f'  → {resp.status_code}')
        try:
            return resp.json(), None, resp.status_code
        except Exception:
            return None, f"не JSON: {resp.text[:300]}", resp.status_code
    except Exception as e:
        log(f'  error: {e}')
        return None, str(e), 0


def get_counter_details(headers, counter_id):
    url = f"{BASE_URL}/management/v1/counter/{counter_id}"
    data, err, status = api_get(url, headers)
    if err or status != 200:
        return None, err, status
    return data, None, status


def print_table(headers, rows):
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


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ === ТЕСТ API ЯНДЕКС.МЕТРИКИ: СПИСОК И ДЕТАЛИ СЧЁТЧИКОВ ===")

    config = load_config()

    token = config.get("oauth_token")
    if not token:
        print()
        print("⚠️  Для запуска скрипта не хватает данных: oauth_token")
        print("ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить")
        return

    log(f'token: {token[:20]}...')

    headers = {"Authorization": f"OAuth {token}"}

    login, login_err = get_login(headers)
    print()
    print("ℹ️  ─── ЛОГИН (API Яндекс ID) ───")
    if login_err:
        print(f"⚠️  Не удалось получить логин: {login_err}")
    else:
        print(f"ℹ️  login: {login}")

    url = f"{BASE_URL}/management/v1/counters"
    data, err, status = api_get(url, headers)

    print()
    print(f"ℹ️  Запрос: GET /management/v1/counters")
    print(f"ℹ️  HTTP: {status}")

    if err:
        print(f"⚠️  Ошибка запроса: {err}")
        return

    if status != 200:
        error_type = data.get("error_type", "")
        message = data.get("message", "")
        print(f"⚠️  Ошибка API ({status}): {error_type} — {message}")
        print()
        print("ℹ️  Полный ответ:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    counters = data.get("counters", [])
    total = data.get("count", len(counters))
    print()
    print(f"ℹ️  Всего счётчиков: {total}")
    print()

    print("ℹ️  ─── ПОЛНЫЙ ОТВЕТ (JSON) ───")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    print()
    print("ℹ️  ─── КОМПАКТНАЯ ТАБЛИЦА ───")
    rows = []
    for c in counters:
        site2 = c.get("site2") or {}
        site = site2.get("site", c.get("site", "-")) or "-"
        owner_login = c.get("owner_login", "")
        permission = c.get("permission", "")
        activity_status = c.get("activity_status", "")
        activity_flag = "⭐" if activity_status == "high" else " "
        match = "✓" if (permission == "own" and owner_login and owner_login == login) else ""
        rows.append([
            c.get("id", ""),
            str(match),
            str(activity_flag),
            c.get("name", ""),
            site,
            owner_login,
            permission,
            activity_status
        ])

    print_table(["id", "✓", "#", "name", "site", "owner_login", "permission", "activity_status"], rows)

    matched = sum(1 for r in rows if r[1] == "✓")
    print()
    print(f"ℹ️  Совпадений owner_login с нашим логином и permission=own: {matched}")

    candidates = [
        c for c in counters
        if c.get("permission") == "own"
        and c.get("owner_login") and c.get("owner_login") == login
    ]

    counter_id = None
    cli_id = None
    if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit():
        cli_id = int(sys.argv[1].lstrip("-"))

    if cli_id is not None and any(c.get("id") == cli_id for c in candidates):
        counter_id = cli_id
    elif cli_id is not None:
        print()
        print(f"⚠️  Переданный id={cli_id} отсутствует среди подходящих счётчиков")
        counter_id = None
    elif len(candidates) == 1:
        counter_id = candidates[0].get("id")
    elif len(candidates) > 1:
        print()
        print(f"⚠️  Вариантов подходящего счётчика больше 1 ({len(candidates)}), выберите вручную:")
        print("ℹ️  Укажите id аргументом: python yandex_metrika_test.py <counter_id>")
        for c in candidates:
            print(f"ℹ️  id={c.get('id')}, name={c.get('name', '')}")

    if counter_id:
        print()
        print("ℹ️  ─── ДЕТАЛИ СЧЁТЧИКА (GET /management/v1/counter/{id}) ───")
        print(f"ℹ️  Запрос: GET /management/v1/counter/{counter_id}")
        details, err, status = get_counter_details(headers, counter_id)
        print(f"ℹ️  HTTP: {status}")
        if err:
            print(f"⚠️  Ошибка запроса: {err}")
        elif status != 200:
            print(f"⚠️  Ошибка API ({status}): {details.get('error_type', '')} — {details.get('message', '')}")
        else:
            counter = details.get("counter") or {}

            mirrors = counter.get("mirrors2") or []
            mirror_rows = []
            for m in mirrors:
                if isinstance(m, dict):
                    mirror_rows.append([
                        m.get("site", ""),
                        m.get("domain", ""),
                        m.get("status", "")
                    ])
                else:
                    mirror_rows.append([str(m), " - ", "?"])

            print()
            if mirror_rows:
                print(f"ℹ️  Зеркала (mirrors2, всего {len(mirror_rows)}):")
                print_table(["site", "domain", "status"], mirror_rows)
            else:
                print("ℹ️  Зеркала (mirrors2): нет")

            statuses = sorted({r[2] for r in mirror_rows if r[2]})
            print()
            if statuses:
                print("ℹ️  ─── КРАТКАЯ СВОДКА: СТАТУСЫ ЗЕРКАЛ В СЧЁТЧИКЕ (уникальные) ───")
                for s in statuses:
                    print(f"ℹ️  • {s}")
            else:
                print("ℹ️  Статусы зеркал: отсутствуют")

    print()
    print("ℹ️ === ТЕСТ ЗАВЕРШЁН ===")
    print(f"ℹ️  Счётчиков в ответе: {len(counters)} из {total}")


if __name__ == "__main__":
    main()