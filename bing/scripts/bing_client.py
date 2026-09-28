"""
bing_client.py — общий модуль Bing Webmaster API (OAuth 2.0).

Хранилище токенов, авто-refresh, вызов методов JSON REST, разбор ошибок
и телеметрия в консоль разработчика GUI (протокол __DEBUG__).

Файлы:
    ../app_config.json  — креды приложения: client_id, client_secret, redirect_uri
    ../accounts.json    — аккаунты: {"accounts": {"email": {"access_token", "refresh_token", "token_expiry"}}}
    ../config.json      — рабочие настройки: {"active_account": "email"}

Документация (Microsoft Learn, IWebmasterApi):
    транспорт — GET/POST /webmaster/api.svc/json/{Метод}, ответ-конверт {"d": ...},
    ошибки — HTTP 400 с {"ErrorCode": N, "Message": "..."}, троттлинг — коды 4/5.
    SOAP/POX выведены из эксплуатации 31.08.2026.

Используется Python-скриптами из bing/scripts/*.py (sys.path[0] == scripts/).
"""
import json
import os
import re
import time

import requests

# OAuth задокументирован на www.bing.com, но примеры методов в справочнике
# используют ssl.bing.com + apikey. Рабочий хост запоминается после первого успеха.
API_HOSTS = (
    "https://www.bing.com/webmaster/api.svc/json",
    "https://ssl.bing.com/webmaster/api.svc/json",
)

# Эндпоинт обмена кода/refresh-токена расходится в документации:
# в тексте — /webmasters/oauth/token, в примере запроса — POST /webmasters/token.
TOKEN_URLS = (
    "https://www.bing.com/webmasters/oauth/token",
    "https://www.bing.com/webmasters/token",
)  

TIMEOUT = 30
TOKEN_TIMEOUT = 20
REFRESH_MARGIN = 60          # обновляем токен за 60 секунд до истечения
RETRIES = 3
RETRY_BACKOFF = (1, 3, 5)
BODY_CUT = 800
PAUSE_BETWEEN_CALLS = 0.4

# Коды ошибок Bing (ApiErrorCode)
API_ERROR_LABELS = {
    0: "Ошибок нет",
    1: "Внутренняя ошибка Bing",
    2: "Неизвестная ошибка",
    3: "Неверный API-ключ (при OAuth такого быть не должно)",
    4: "Троттлинг по пользователю (слишком много запросов)",
    5: "Троттлинг по сайту (слишком много запросов к сайту)",
    6: "Аккаунт заблокирован",
    7: "Неверный URL сайта",
    8: "Неверный параметр запроса",
    9: "Превышен лимит сайтов у аккаунта",
    10: "Пользователь не найден",
    11: "Не найдено (сайт, фид или URL не существует)",
    12: "Уже существует",
    13: "Операция не разрешена",
    14: "Нет прав на операцию (токен без нужного scope или чужой аккаунт)",
    15: "Неожиданное состояние",
    16: "Метод объявлен устаревшим (Deprecated)",
}

THROTTLE_CODES = (5,)
RETRY_HTTP = (429, 500, 502, 503, 504)

# Верхняя граница даты для ms_date: 01.01.2100 в миллисекундах.
# Нижняя — эпоха (0): всё, что вне диапазона, — служебные MinValue/MaxValue Bing.
DATE_MAX = 4102444800000

_ROLE_LABELS = {0: "Администратор", 1: "Только чтение", 2: "Чтение и запись"}

_DIR = os.path.dirname(os.path.abspath(__file__))
_active_host = API_HOSTS[0]
_token = ""


def dbg(tag, msg, **fields):
    """Техническая телеметрия → консоль разработчика GUI (протокол __DEBUG__)."""
    payload = {"tag": tag, "msg": msg}
    payload.update(fields)
    try:
        print(f'__DEBUG__:{json.dumps(payload, ensure_ascii=False)}', flush=True)
    except Exception:
        pass


def _read_json(path, empty):
    if not os.path.exists(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return empty


def _write_json(path, data):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ======================== КОНФИГИ ========================

def load_app_config():
    """Данные приложения Bing: client_id, client_secret, redirect_uri, scope."""
    return _read_json(os.path.join(_DIR, '..', 'app_config.json'), {}) or None


def load_config():
    return _read_json(os.path.join(_DIR, '..', 'config.json'), {})


def load_accounts():
    """dict email -> {access_token, refresh_token, token_expiry}"""
    data = _read_json(os.path.join(_DIR, '..', 'accounts.json'), {})
    if isinstance(data, dict):
        accounts = data.get("accounts", data)
        if isinstance(accounts, dict):
            return accounts
    return {}


def save_accounts(accounts):
    _write_json(os.path.join(_DIR, '..', 'accounts.json'), {"accounts": accounts})


def get_active_account():
    return (load_config().get("active_account") or "").strip()


# ======================== УТИЛИТЫ ========================

def host_of(url):
    """Хост из URL (или из голого домена) в нижнем регистре."""
    url = (url or '').strip()
    if not url:
        return ''
    if url.startswith('domain:'):
        url = url[len('domain:'):]
    if '://' not in url:
        url = 'https://' + url
    return (url.split('://', 1)[1].split('/')[0].split('?')[0] or '').lower()


def site_root(site_url):
    """Корень сайта для методов уровня URL."""
    site_url = (site_url or '').strip()
    if not site_url:
        return ''
    return site_url if site_url.endswith('/') else site_url + '/'


def ms_date(value):
    """/Date(1314031258933-0700)/ или ISO-строка → 'дд.мм.гггг чч:мм'.

    Bing отдаёт для незаполненных дат DateTime.MinValue (/Date(-62135568000000-0700)/)
    и MaxValue — они вне диапазона time_t, time.localtime на Windows падает с
    OSError [Errno 22]. Такие значения (и любые вне 1970..2100) заменяем на '—'.
    """
    if not value:
        return ''
    text = str(value)
    match = re.search(r'/Date\((-?\d+)', text)
    if match:
        ms = int(match.group(1))
        if not 0 <= ms <= DATE_MAX:
            return '—'
        try:
            return time.strftime('%d.%m.%Y %H:%M', time.localtime(ms // 1000))
        except (OSError, ValueError, OverflowError):
            return '—'
    if re.match(r'^\d{4}-\d{2}-\d{2}', text):
        return text.replace('T', ' ')[:16]
    return text


def _safe_json(text):
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def error_code_of(payload):
    """Код ошибки Bing из тела ответа."""
    if not isinstance(payload, dict):
        return 0
    for key in ("ErrorCode", "errorCode"):
        if key in payload:
            try:
                return int(payload.get(key) or 0)
            except Exception:
                return 0
    inner = payload.get("d")
    if isinstance(inner, dict):
        return error_code_of(inner)
    return 0


def describe_error(status, payload, body_text):
    """Человекочитаемое описание ошибки: 'HTTP 400: код 11 — Не найдено…: NotFound'."""
    code = error_code_of(payload)
    message = ''
    if isinstance(payload, dict):
        for source in (payload, payload.get("d") if isinstance(payload.get("d"), dict) else {}):
            for key in ("Message", "message", "ErrorMessage"):
                if source.get(key):
                    message = str(source[key])
                    break
            if message:
                break
    if not message:
        message = (body_text or '').strip()[:BODY_CUT]

    parts = [f"HTTP {status}"]
    if code:
        label = API_ERROR_LABELS.get(code, "")
        parts.append(f"код {code}" + (f" — {label}" if label else ""))
    if message and message not in (f"HTTP {status}", ''):
        parts.append(message)
    return ": ".join(parts)


def crawl_issue_labels(mask):
    """Битовая маска UrlWithCrawlIssues.CrawlIssues → список названий."""
    bits = (
        (1, "301"), (2, "302"), (4, "4xx"), (8, "5xx"), (16, "robots.txt"),
        (32, "вредоносное ПО"), (64, "важный URL закрыт в robots.txt"),
        (128, "ошибки DNS"), (256, "таймауты"),
    )
    try:
        mask = int(mask or 0)
    except Exception:
        return str(mask)
    if not mask:
        return "нет"
    return ", ".join(name for bit, name in bits if mask & bit) or f"неизвестная маска {mask}"


def role_label(value):
    try:
        value = int(value)
    except Exception:
        return str(value)
    return _ROLE_LABELS.get(value, f"роль {value}")


# ======================== ТОКЕНЫ ========================

def _refresh_access_token(app, account):
    """grant_type=refresh_token. Новый refresh_token может не прийти — сохраняем прежний."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": account.get("refresh_token", ""),
        "client_id": (app.get("client_id") or "").strip(),
        "client_secret": (app.get("client_secret") or "").strip(),
    }
    redirect_uri = (app.get("redirect_uri") or "").strip()
    if redirect_uri:
        data["redirect_uri"] = redirect_uri

    last_error = ""
    for url in TOKEN_URLS:
        try:
            resp = requests.post(url, data=data, timeout=TOKEN_TIMEOUT)
        except Exception as e:
            last_error = f"{url}: {type(e).__name__}: {e}"
            dbg("TOKEN", "ошибка запроса refresh", url=url, error_type=type(e).__name__, detail=str(e))
            continue

        if resp.status_code == 200:
            try:
                tokens = resp.json()
            except Exception as e:
                last_error = f"{url}: не удалось разобрать ответ ({e})"
                continue
            access_token = tokens.get("access_token") or ""
            if not access_token:
                last_error = f"{url}: в ответе нет access_token"
                continue
            account["access_token"] = access_token
            account["token_expiry"] = int(time.time()) + int(tokens.get("expires_in") or 3599) - REFRESH_MARGIN
            if tokens.get("refresh_token"):
                account["refresh_token"] = tokens["refresh_token"]
            dbg("TOKEN", "токен обновлён", url=url, expires_in=tokens.get("expires_in"),
                refresh_rotated=bool(tokens.get("refresh_token")))
            return account

        last_error = f"{url}: HTTP {resp.status_code} {resp.text[:200]}"
        dbg("TOKEN", "refresh не подошёл", url=url, status=resp.status_code,
            body=(resp.text or "")[:BODY_CUT])
    raise RuntimeError(f"Не удалось обновить токен Bing: {last_error}")


def get_access_token():
    """
    Возвращает (access_token, email) для активного аккаунта или (None, сообщение_об_ошибке).
    При истёкшем token_expiry обновляет access_token в accounts.json.
    """
    email = get_active_account()
    if not email:
        return None, ("Не выбран аккаунт Bing (active_account в bing/config.json). "
                      "Авторизуйтесь на вкладке Bing → Авторизоваться")

    accounts = load_accounts()
    account = accounts.get(email)
    if not account:
        return None, f"Для аккаунта {email} нет токенов в bing/accounts.json — авторизуйтесь заново"
    if not account.get("refresh_token"):
        return None, f"У аккаунта {email} отсутствует refresh_token — авторизуйтесь заново"

    stale = (not account.get("access_token")) or \
        not account.get("token_expiry") or \
        account["token_expiry"] <= time.time() + REFRESH_MARGIN

    if stale:
        app = load_app_config()
        if not app:
            return None, "Не найден bing/app_config.json (данные приложения Bing)"
        try:
            account = _refresh_access_token(app, account)
        except Exception as e:
            return None, str(e)
        accounts[email] = account
        save_accounts(accounts)

    return account["access_token"], email


# ======================== ВЫЗОВ МЕТОДОВ ========================

def set_token(token):
    """Токен для последующих вызовов call() — ставится скриптом после get_access_token()."""
    global _token
    _token = token or ""


def call(method, params=None, body=None, pause=True):
    """
    Вызов метода Bing Webmaster API.

    Возвращает (ok, data, error_str):
        ok=True  → data = payload["d"] (список, словарь или None для void-методов)
        ok=False → error_str = 'HTTP 400: код 11 — Не найдено…: NotFound'

    При 401 на основном хосте ИЛИ при сетевых ошибках (DNS, timeout, connection)
    запрос повторяется на ssl.bing.com.
    Ретраи — на троттлинг (ErrorCode 4/5), 429 и 5xx.
    """
    global _active_host

    hosts = [_active_host] if _active_host in API_HOSTS else [API_HOSTS[0]]
    if API_HOSTS[1] not in hosts:
        hosts.append(API_HOSTS[1])

    last_error = ""
    for host in hosts:
        url = f"{host}/{method}"
        headers = {
            "Authorization": f"Bearer {_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        switch_host = False
        for attempt in range(1, RETRIES + 1):
            if pause:
                time.sleep(PAUSE_BETWEEN_CALLS)
            start = time.time()
            try:
                if body is None:
                    resp = requests.get(url, params=params or {}, headers=headers, timeout=TIMEOUT)
                else:
                    resp = requests.post(url, params=params or {}, headers=headers,
                                         data=json.dumps(body), timeout=TIMEOUT)
            except requests.exceptions.RequestException as e:
                # Сетевые ошибки (DNS, timeout, connection) → пробуем следующий хост
                last_error = f"{type(e).__name__}: {e}"
                dbg("API", "сетевая ошибка", method=method, host=host, attempt=attempt,
                    error_type=type(e).__name__, detail=str(e), elapsed=round(time.time() - start, 2))
                if attempt < RETRIES:
                    time.sleep(RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)])
                    continue
                # Ретраи исчерпаны на этом хосте → переключаемся на следующий
                switch_host = True
                break

            status = resp.status_code
            body_text = resp.text or ''
            elapsed = round(time.time() - start, 2)
            payload = _safe_json(body_text)

            if status == 200:
                dbg("API", "ok", method=method, host=host, status=status, elapsed=elapsed,
                    body_len=len(body_text))
                _active_host = host
                return True, (payload or {}).get("d"), ""

            if status == 401 and host == API_HOSTS[0]:
                dbg("API", "401 на основном хосте — пробуем ssl.bing.com", method=method, status=status)
                switch_host = True
                break

            code = error_code_of(payload)
            last_error = describe_error(status, payload, body_text)
            dbg("API", "ошибка", method=method, host=host, status=status, elapsed=elapsed,
                error_code=code, body=body_text[:BODY_CUT])

            if (code in THROTTLE_CODES or status in RETRY_HTTP) and attempt < RETRIES:
                time.sleep(RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)])
                continue
            break
        # Переход на второй хост: после 401 ИЛИ после сетевых ошибок (switch_host=True)
        if switch_host:
            continue
        break
    return False, None, last_error or "Неизвестная ошибка Bing"
