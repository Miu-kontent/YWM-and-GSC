import json
import os
import sys
import requests

BASE_URL = "https://api-metrika.yandex.net"
INFO_URL = "https://login.yandex.ru/info"


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()

    token = config.get("oauth_token")
    if not token:
        print()
        print("⚠️  Для запуска скрипта не хватает данных: oauth_token")
        print("ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить")
        return

    headers = {"Authorization": f"OAuth {token}"}

    try:
        resp = requests.get(INFO_URL, headers=headers, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка запроса к Яндекс ID: {e}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"❌ Не удалось получить логин: HTTP {resp.status_code}")
        sys.exit(1)

    login = resp.json().get("login", "")
    if not login:
        print("❌ Пустой login в ответе Яндекс ID")
        sys.exit(1)

    print(f"ℹ️  Логин: {login}")

    try:
        resp = requests.get(f"{BASE_URL}/management/v1/counters", headers=headers, timeout=15)
    except Exception as e:
        print(f"❌ Ошибка запроса к API Метрики: {e}")
        sys.exit(1)

    if resp.status_code != 200:
        try:
            body = resp.json()
            err = f"{body.get('error_type', '')} — {body.get('message', '')}".strip(" —")
        except Exception:
            err = resp.text[:300]
        print(f"❌ Ошибка API Метрики (HTTP {resp.status_code}): {err}")
        sys.exit(1)

    counters = resp.json().get("counters", [])

    candidates = []
    for c in counters:
        owner_login = c.get("owner_login", "")
        permission = c.get("permission", "")
        if permission == "own" and owner_login and owner_login == login:
            site2 = c.get("site2") or {}
            site = site2.get("site", c.get("site", "")) or ""
            candidates.append({
                "id": c.get("id"),
                "name": c.get("name", ""),
                "site": site,
                "status": c.get("status", ""),
                "activity_status": c.get("activity_status", ""),
                "permission": permission,
                "owner_login": owner_login
            })

    if not candidates:
        print()
        print("⚠️  Подходящих счётчиков не найдено")
        print("ℹ️  Проверьте, что у счётчика permission=own и owner_login совпадает с вашим логином")
        return

    if len(candidates) == 1:
        cand = candidates[0]
        print()
        print(f"✅ Счётчик найден: id={cand['id']}, name={cand['name']}, site={cand['site']}")
        print(f"METRIKA_ID:{cand['id']}")
        return

    print()
    print(f"⚠️  Вариантов подходящего счётчика больше 1 ({len(candidates)}), выберите счётчик вручную")
    print()
    for i, cand in enumerate(candidates, 1):
        print(f"ℹ️  {i}. id={cand['id']}, name={cand['name']}, site={cand['site']}, "
              f"status={cand['status']}, activity_status={cand['activity_status']}")


if __name__ == "__main__":
    main()