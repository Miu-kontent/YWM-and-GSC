"""
gsc_client.py — общий модуль Google Search Console (Desktop OAuth).

Загрузка конфигов, авторизация, обновление токенов и построение сервисов
google-api-python-client (webmasters v3 + siteVerification v1 + searchconsole v1).

Файлы:
    ../app_config.json  — креды Desktop-приложения (installed.client_id/secret/token_uri)
    ../accounts.json    — аккаунты: {"accounts": {"email": {"access_token", "refresh_token", "token_expiry"}}}
    ../config.json      — рабочие настройки: {"active_account": "email", "sitemap_path": "..."}

Используется Python-скриптами из google/scripts/*.py (sys.path[0] == scripts/).
"""
import datetime
import json
import os
from urllib.parse import urlparse

SCOPES = [
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/siteverification",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

_DIR = os.path.dirname(__file__)


def _read_json(path, empty):
    if not os.path.exists(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return empty


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ======================== КОНФИГИ ========================

def load_app_config():
    """Данные Desktop-приложения (client_id, client_secret, token_uri, project_id)."""
    data = _read_json(os.path.join(_DIR, '..', 'app_config.json'), {})
    for key in ("installed", "web"):
        if key in data:
            return data[key]
    return None


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

def normalize_site_url(url):
    """GSC-ресурс на уровне хоста: scheme://host (sc-domain: оставляем как есть)."""
    url = (url or '').strip()
    if not url:
        return ''
    if url.startswith('sc-domain:'):
        return url
    if '://' not in url:
        url = 'https://' + url
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if not host:
        return ''
    return f"{parsed.scheme.lower()}://{host}"


def property_key(url):
    """Канонический ключ GSC-ресурса с сохранением пути.

    sc-domain:ALCO.REHAB            → 'sc-domain:alco.rehab'
    https://alco.rehab/              → 'https://alco.rehab'
    https://alco.rehab/regions/znamensk/ → 'https://alco.rehab/regions/znamensk'
    'alco.rehab' (голый домен)       → 'https://alco.rehab'
    """
    url = (url or '').strip()
    if not url:
        return ''
    if url.startswith('sc-domain:'):
        host = url[len('sc-domain:'):].strip().lower()
        return f'sc-domain:{host}' if host else ''
    if '://' not in url:
        url = 'https://' + url
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if not host:
        return ''
    key = f'{parsed.scheme.lower()}://{host.lower()}{parsed.path or ""}'
    return key.rstrip('/') if key.endswith('/') else key


def build_site_url(raw):
    """Ввод → GSC-ресурс (URL-prefix или sc-domain), путь сохраняется.

    'alco.rehab'                     → 'https://alco.rehab/'
    'https://alco.rehab/regions/…/'  → 'https://alco.rehab/regions/…/'
    'sc-domain:alco.rehab'           → 'sc-domain:alco.rehab'
    """
    raw = (raw or '').strip()
    if not raw:
        return ''
    if raw.lower().startswith('sc-domain:'):
        host = raw[len('sc-domain:'):].strip().lower()
        return f'sc-domain:{host}' if host else ''
    key = property_key(raw)
    if not key:
        return ''
    return key + '/'


def resolve_entries(site_entries, raw):
    """Выбор списка GSC-ресурсов под ввод raw (точное совпадение по полному ключу).

    - голый домен / корневой https://host/  → сопоставляется ТОЛЬКО хостовому
      URL-prefix ресурсу (sc-domain: и ресурсы с путём не матчатся);
    - URL с путём https://host/path/         → ровно этот ресурс;
    - sc-domain:host                         → ровно sc-domain-ресурс.
    Возвращает пустой список, если совпадений нет (без префиксных фолбэков).
    """
    raw = (raw or '').strip()
    if not raw or not site_entries:
        return []
    want = property_key(raw)
    if not want:
        return []
    return [e for e in site_entries if property_key(e.get('siteUrl', '')) == want]


def api_error_str(e):
    """Человекочитаемое описание ошибки API Google."""
    try:
        from googleapiclient.errors import HttpError
        if isinstance(e, HttpError):
            try:
                data = json.loads(e.content.decode('utf-8'))
                err = data.get('error', {})
                msg = err.get('message') or err.get('status') or e.resp.reason
                return f"HTTP {e.resp.status}: {msg}"
            except Exception:
                return f"HTTP {e.resp.status}: {e.resp.reason}"
    except Exception:
        pass
    return str(e)


# ======================== КРЕДЕНЦИАЛЫ / СЕРВИСЫ ========================

def get_credentials():
    """
    Возвращает (credentials, email) для активного аккаунта или (None, сообщение_ошибки).
    Обновляет access_token в accounts.json при истечении/отсутствии.
    """
    app = load_app_config()
    if not app:
        return None, "Не найден google/app_config.json (данные Desktop-приложения)"

    email = get_active_account()
    if not email:
        return None, "Не выбран аккаунт Google (active_account в google/config.json). Авторизуйтесь кнопкой 'Авторизоваться'"

    accounts = load_accounts()
    acc = accounts.get(email)
    if not acc:
        return None, f"Для аккаунта {email} нет токенов в google/accounts.json — авторизуйтесь заново"
    if not acc.get("refresh_token"):
        return None, f"У аккаунта {email} отсутствует refresh_token — авторизуйтесь заново"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        return None, "Не установлены google-auth-oauthlib / google-api-python-client. Установите: pip install -r requirements.txt"

    expiry = None
    if acc.get("token_expiry"):
        expiry = datetime.datetime.fromtimestamp(acc["token_expiry"], tz=datetime.timezone.utc)

    creds = Credentials(
        token=acc.get("access_token"),
        refresh_token=acc.get("refresh_token"),
        token_uri=app.get("token_uri"),
        client_id=app.get("client_id"),
        client_secret=app.get("client_secret"),
        scopes=SCOPES,
        expiry=expiry,
    )

    stale = (not creds.token) or expiry is None or datetime.datetime.now(datetime.timezone.utc) >= expiry
    if stale:
        try:
            creds.refresh(Request())
        except Exception as e:
            return None, f"Не удалось обновить токен аккаунта {email}: {e}"
        acc["access_token"] = creds.token
        acc["token_expiry"] = int(creds.expiry.timestamp()) if creds.expiry else None
        save_accounts(accounts)

    return creds, email


def build_services():
    """
    Возвращает (webmasters_service, siteverification_service, searchconsole_service, email)
    или (None, None, None, сообщение_об_ошибке).

    searchconsole v1 нужен для urlInspection (отдельный базовый URL).
    """
    creds, info = get_credentials()
    if not creds:
        return None, None, None, info
    try:
        from googleapiclient.discovery import build
        webmasters = build("webmasters", "v3", credentials=creds, cache_discovery=False)
        site_verification = build("siteVerification", "v1", credentials=creds, cache_discovery=False)
        searchconsole = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        return webmasters, site_verification, searchconsole, info
    except Exception as e:
        return None, None, None, f"Ошибка создания сервисов Google API: {e}"