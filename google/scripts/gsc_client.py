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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    global _last_credentials
    _last_credentials = creds
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


# ======================== ПАРАЛЛЕЛЬНЫЙ ПРОГОН ========================

# Потолок задаёт квота Google на пользователя: 20 QPS для webmasters v3
# («all other resources»: sites.list, sitemaps.list). Выше этого распараллеливание
# упирается в квоту, а не в сеть, поэтому темп держим ниже, а число потоков скромное.
MAX_WORKERS = 5        # потоков по умолчанию
RATE_LIMIT_RPS = 15.0  # ограничитель темпа запросов (на все потоки сразу)
RATE_RETRIES = 3       # ретраи на 429/403 по квоте частоты
RATE_BACKOFF = 3.0     # пауза перед первым ретраем, далее x2

# Креды активного аккаунта — для поточных сервисов (заполняется get_credentials()).
_last_credentials = None

# Отдельный webmasters-сервис на поток: httplib2 не потокобезопасен и держит
# одно соединение на хост (conn_key = scheme + ':' + authority), поэтому общий
# сервис схлопнул бы все потоки в одно keep-alive соединение.
_local = threading.local()


class _RateLimiter:
    """Ограничитель темпа запросов, общий для потоков (token-bucket под Lock)."""

    def __init__(self, rps):
        self._interval = 1.0 / rps if rps and rps > 0 else 0.0
        self._lock = threading.Lock()
        self._next_at = 0.0

    def acquire(self):
        if self._interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self._interval
        if wait > 0:
            time.sleep(wait)


def rate_limiter(rps=None):
    """Ограничитель темпа. rps=None → RATE_LIMIT_RPS; rps<=0 → без ограничения."""
    return _RateLimiter(RATE_LIMIT_RPS if rps is None else rps)


def thread_webmasters():
    """Свой webmasters-сервис на поток вызывающего (см. комментарий к _local)."""
    global _last_credentials
    creds = _last_credentials
    if creds is None:
        creds, info = get_credentials()
        if creds is None:
            raise RuntimeError(info)
    svc = getattr(_local, "webmasters", None)
    if svc is None:
        from googleapiclient.discovery import build
        svc = build("webmasters", "v3", credentials=creds, cache_discovery=False)
        _local.webmasters = svc
    return svc


def rate_limit_reason(e):
    """Поле reason из тела ошибки Google ('' — разобрать не удалось)."""
    try:
        from googleapiclient.errors import HttpError
        if not isinstance(e, HttpError):
            return ""
        data = json.loads(e.content.decode("utf-8"))
        err = data.get("error", {}) or {}
        for item in (err.get("errors") or []):
            if item.get("reason"):
                return item["reason"]
        return err.get("status") or ""
    except Exception:
        return ""


def is_rate_limit_error(e):
    """429 — всегда; 403 — только по квоте частоты.

    quotaExceeded сюда НЕ входит: это дневная квота / лимит сайтов, ретрай бесполезен
    (то же, что is_limit_error в gsc_add_sites.py).
    """
    try:
        from googleapiclient.errors import HttpError
        if not isinstance(e, HttpError):
            return False
        status = int(e.resp.status)
        if status == 429:
            return True
        if status == 403:
            return rate_limit_reason(e) in ("rateLimitExceeded", "userRateLimitExceeded")
        return False
    except Exception:
        return False


def retry_on_quota(func, limiter=None, retries=None):
    """Вызов API с ограничением темпа и ретраями на 429/403 по квоте частоты.

    func() — замыкание без аргументов (сам запрос). Ошибка, которая не является
    ошибкой частоты, пробрасывается сразу.
    """
    limiter = limiter or rate_limiter()
    retries = RATE_RETRIES if retries is None else retries
    wait = RATE_BACKOFF
    for attempt in range(1, retries + 1):
        limiter.acquire()
        try:
            return func()
        except Exception as e:
            if attempt >= retries or not is_rate_limit_error(e):
                raise
            reason = rate_limit_reason(e) or "rate limit"
            print(f"⏳ Лимит запросов Google ({reason}), ждём {wait:.0f} сек... "
                  f"(попытка {attempt}/{retries})", flush=True)
            time.sleep(wait)
            wait *= 2


def run_parallel(items, worker, max_workers=None):
    """Параллельный вызов worker(item, idx) с выдачей результатов в порядке items.

    worker(item, idx) выполняется в пуле потоков, а отдача (idx, результат) идёт
    строго в порядке входа — печать __TABLE_ROW__ остаётся в главном потоке, и
    порядок строк отчёта не «плывёт». Исключения из worker пробрасываются
    в вызывающий поток (future.result()).

    max_workers=None → MAX_WORKERS; 1 → обычный последовательный цикл без пула.
    """
    items = list(items)
    total = len(items)
    if total == 0:
        return

    workers = MAX_WORKERS if max_workers is None else max(1, int(max_workers))
    if workers == 1 or total == 1:
        for idx, item in enumerate(items):
            yield idx, worker(item, idx)
        return

    results = {}
    next_idx = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, item, idx): idx for idx, item in enumerate(items)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
            while next_idx in results:
                yield next_idx, results.pop(next_idx)
                next_idx += 1