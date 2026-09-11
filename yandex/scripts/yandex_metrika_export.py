import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

BASE_URL = "https://api-metrika.yandex.net"

SITE_STATUS_LABELS = {
    "": "Не привязан",
    "ok": "Привязан",
    "need_webmaster_confirm": "Ожидает подтверждения",
    "deleted": "Откреплён",
}

PROBLEM_STATUSES = ("need_webmaster_confirm", "deleted")


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)


def load_script_data():
    array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'yandex_metrika_export.json')
    if not os.path.exists(array_path):
        return {}
    try:
        with open(array_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def normalize_host(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def api_get(url, headers, params=None, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            try:
                return resp.json(), None, resp.status_code
            except Exception:
                return None, f"не JSON: {resp.text[:300]}", resp.status_code
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, f"Превышен таймаут ({timeout}с)", 0
            time.sleep(1)
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e), 0
            time.sleep(1)
    return None, "Unknown error", 0


def mirror_to_entry(m):
    if isinstance(m, dict):
        site = m.get('site') or m.get('domain') or ''
        status = m.get('status', '')
    else:
        site = str(m)
        status = ''
    return {'site': site or '-', 'status': status, 'key': normalize_host(site)}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    print("ℹ️ === ВЫГРУЗКА ЗЕРКАЛ СЧЁТЧИКА МЕТРИКИ ===")

    config = load_config()
    script_data = load_script_data()

    token = config.get("oauth_token")
    if not token:
        print()
        print("⚠️  Для запуска скрипта не хватает данных: oauth_token")
        print("ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить")
        return

    metric_id = config.get("metric_id")
    if not metric_id:
        print()
        print("⚠️  Для запуска скрипта не хватает данных: metric_id")
        print("ℹ️  Получите номер счётчика кнопкой 'Получить' на вкладке Яндекс → Ключи")
        return

    links_raw = script_data.get("links", "")
    if isinstance(links_raw, str):
        user_sites = [normalize_host(s) for s in links_raw.strip().split('\n') if s.strip()]
    elif isinstance(links_raw, list):
        user_sites = [normalize_host(s) for s in links_raw if str(s).strip()]
    else:
        user_sites = []

    headers = {"Authorization": f"OAuth {token}"}

    print(f"ℹ️  Выбранный счётчик: {metric_id}")
    if user_sites:
        print(f"ℹ️  Фильтр по сайтам: {len(user_sites)} шт.")
    print()
    print("ℹ️  Получаю список счётчиков (GET /counters)...")

    counters_data, err, status = api_get(f"{BASE_URL}/management/v1/counters", headers)
    if err or status != 200:
        message = (counters_data or {}).get('message', err or f"HTTP {status}")
        print(f"⚠️  Ошибка запроса счётчиков: {message}")
        return

    counters = counters_data.get("counters", []) or []
    total_counters = counters_data.get("count", len(counters))
    print(f"ℹ️  Количество счетчиков: {total_counters}")

    print()
    print(f"ℹ️  Получаю данные счётчика (GET /counter/{metric_id})...")
    detail_data, err, status = api_get(f"{BASE_URL}/management/v1/counter/{metric_id}", headers)
    if err or status != 200:
        message = (detail_data or {}).get('message', err or f"HTTP {status}")
        print(f"⚠️  Ошибка запроса счётчика: {message}")
        return

    counter = detail_data.get("counter", {}) or {}
    mirrors = counter.get("mirrors2", []) or []

    entries = [mirror_to_entry(m) for m in mirrors]

    if user_sites:
        user_index = {s: i for i, s in enumerate(user_sites)}
        entries = [e for e in entries if e['key'] and e['key'] in user_index]
        entries.sort(key=lambda e: user_index.get(e['key'], 0))

    total = len(entries)
    bound = sum(1 for e in entries if e['status'] == 'ok')
    unbound = sum(1 for e in entries if e['status'] == '')
    problem = sum(1 for e in entries if e['status'] in PROBLEM_STATUSES)

    print()
    print(f"ℹ️  Сайтов в выгрузке: {total}")
    print()

    for e in entries:
        label = SITE_STATUS_LABELS.get(e['status'])
        if label is None:
            label = f"Статус: {e['status']}"
        if e['status'] == 'ok':
            label = f"✅ {label}"
        elif e['status'] == 'need_webmaster_confirm':
            label = f"⚠️ {label}"
        print(f"__TABLE_ROW__:{json.dumps({'cells': [e['site'], label]}, ensure_ascii=False)}")

    print()
    summary = {
        "Количество счетчиков": total_counters,
        "Номер выбранного счётчика": str(metric_id),
        "Количество сайтов": total,
        "Привязанных": bound,
        "Не привязанных": unbound,
        "Проблемных": problem
    }
    print(f"__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}")
    print("__TABLE_DONE__:{}")

    print()
    print("ℹ️ === ВЫГРУЗКА ЗАВЕРШЕНА ===")


if __name__ == "__main__":
    main()