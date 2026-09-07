import json
import os
import sys
import requests


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)

    token = config.get("oauth_token")
    if not token:
        print("❌ Сначала получите OAuth Token")
        sys.exit(1)

    headers = {"Authorization": f"OAuth {token}"}
    try:
        resp = requests.get("https://api.webmaster.yandex.net/v4/user/", headers=headers, timeout=10)
        if resp.status_code == 200:
            user_id = str(resp.json().get("user_id", ""))
            print(f"✅ user_id: {user_id}")
            print(f"USER_ID:{user_id}")
        else:
            print(f"❌ Ошибка API: HTTP {resp.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
