import json
import os
import sys
import time
import requests
import websocket

CDP_URL = "http://127.0.0.1:9229"
OAUTH_URL = "https://oauth.yandex.ru/authorize?response_type=token&client_id={client_id}"
TOKEN_SELECTOR = ".verification-code-flow-token-output"


def is_browser_running():
    try:
        r = requests.get(f"{CDP_URL}/json/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def get_page_ws_url():
    r = requests.get(f"{CDP_URL}/json", timeout=5)
    pages = r.json()
    for page in pages:
        if page.get("type") == "page":
            return page.get("webSocketDebuggerUrl", "")
    return ""


def cdp_send(ws, method, params=None, msg_id=None):
    if msg_id is None:
        msg_id = int(time.time() * 1000) % 1000000
    msg = {"id": msg_id, "method": method}
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))
    return msg_id


def drain_messages(ws, timeout=0.5):
    ws.settimeout(timeout)
    while True:
        try:
            ws.recv()
        except Exception:
            break


def wait_for_token(ws, timeout=180):
    poll_id = 77777
    start = time.time()
    while time.time() - start < timeout:
        try:
            cdp_send(ws, "Runtime.evaluate", {
                "expression": f"document.querySelector('{TOKEN_SELECTOR}')?.textContent || ''",
                "returnByValue": True
            }, poll_id)

            ws.settimeout(3)
            while True:
                raw = ws.recv()
                resp = json.loads(raw)
                if resp.get("id") == poll_id:
                    token = resp.get("result", {}).get("result", {}).get("value", "").strip()
                    if token:
                        return token
                    break
        except websocket.WebSocketTimeoutException:
            pass
        except Exception as e:
            print(f"⚠️ Ошибка опроса: {e}")

        time.sleep(2)

    return None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config_path = os.path.join(os.path.dirname(__file__), '..', 'app_config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            app_config = json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения app_config.json: {e}")
        sys.exit(1)

    client_id = app_config.get("client_id")
    if not client_id:
        print("❌ client_id не найден в app_config.json")
        sys.exit(1)

    auth_url = OAUTH_URL.format(client_id=client_id)

    if not is_browser_running():
        print("⚠️ Браузер не запущен. Откройте браузер кнопкой '🌐 Браузер (порт 9229)' и повторите попытку.")
        sys.exit(1)

    print("🌐 Подключаемся к браузеру...")

    ws_url = get_page_ws_url()
    if not ws_url:
        print("❌ Не удалось найти открытую страницу в браузере")
        sys.exit(1)

    print(f"ℹ️ WebSocket: {ws_url[:80]}...")

    try:
        ws = websocket.create_connection(ws_url, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка подключения WebSocket: {e}")
        sys.exit(1)

    print("✅ Подключено")

    cdp_send(ws, "Page.enable", msg_id=1)
    drain_messages(ws, timeout=1)

    cdp_send(ws, "Page.navigate", {"url": auth_url}, msg_id=2)
    drain_messages(ws, timeout=2)

    print("🔐 Авторизуйтесь в браузере (или закройте окно авторизации)...")
    print("⏳ Ожидание получения токена (до 180 сек)...")

    token = wait_for_token(ws, timeout=180)
    ws.close()

    if not token:
        print("❌ Таймаут: токен не получен (180 сек)")
        sys.exit(1)

    print(f"✅ Токен получен")
    print(f"OAUTH_TOKEN:{token}")

if __name__ == "__main__":
    main()
