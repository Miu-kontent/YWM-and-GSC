"""
yandex_client.py — общий модуль Яндекс.Вебмастера / Метрики (аккаунты).

Загрузка конфигов и разрешение активного аккаунта в токен + user_id.

Файлы:
    ../app_config.json  — данные OAuth-приложения: {"client_id": "...", "client_secret": ""}
    ../accounts.json    — аккаунты: {"accounts": {"<login>": {"oauth_token": ..., "user_id": ...}}}
    ../config.json      — рабочие настройки: {"active_account": "<login>", "metric_id": "...",
                                                "contact_path": "...", "sitemap_path": "..."}

Ключевая функция — load_config(): возвращает config.json с ПОДМЕШАННЫМИ oauth_token/user_id
активного аккаунта из accounts.json, поэтому существующие скрипты (config.get('oauth_token'))
работают без изменения внутренней логики.

Используется Python-скриптами из yandex/scripts/*.py (sys.path[0] == scripts/).
"""
import json
import os

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
    """Данные OAuth-приложения (client_id, client_secret)."""
    return _read_json(os.path.join(_DIR, '..', 'app_config.json'), {})


def load_config():
    """
    Рабочие настройки (config.json) с подмешанными oauth_token/user_id активного аккаунта.
    Если активный аккаунт не задан — ключи остаются пустыми (скрипт сообщит о нехватке данных).
    """
    cfg = _read_json(os.path.join(_DIR, '..', 'config.json'), {}) or {}
    acc = get_active_account_data()
    if acc:
        cfg.setdefault('oauth_token', '')
        cfg.setdefault('user_id', '')
        cfg['oauth_token'] = acc.get('oauth_token', '')
        cfg['user_id'] = acc.get('user_id', '')
    return cfg


def load_accounts():
    """dict <login> -> {oauth_token, user_id}"""
    data = _read_json(os.path.join(_DIR, '..', 'accounts.json'), {})
    if isinstance(data, dict):
        accounts = data.get("accounts", data)
        if isinstance(accounts, dict):
            return accounts
    return {}


def save_accounts(accounts):
    _write_json(os.path.join(_DIR, '..', 'accounts.json'), {"accounts": accounts})


def get_active_account():
    """Логин активного аккаунта из config.json (без подмешивания токенов)."""
    return (get_raw_config().get("active_account") or "").strip()


def get_raw_config():
    """config.json как есть, без подмешивания токенов."""
    return _read_json(os.path.join(_DIR, '..', 'config.json'), {})


def get_active_account_data():
    """dict {login, oauth_token, user_id} активного аккаунта или None."""
    login = get_active_account()
    if not login:
        return None
    acc = load_accounts().get(login) or {}
    if not acc.get('oauth_token'):
        return None
    return {
        "login": login,
        "oauth_token": acc.get('oauth_token', ''),
        "user_id": acc.get('user_id', ''),
    }


def get_credentials():
    """
    Возвращает (oauth_token, user_id, login) активного аккаунта
    или (None, None, сообщение_об_ошибке).
    """
    acc = get_active_account_data()
    if not acc:
        return None, None, "Не выбран аккаунт Яндекс (active_account в yandex/config.json). Авторизуйтесь кнопкой 'Авторизоваться'"
    return acc['oauth_token'], acc['user_id'], acc['login']