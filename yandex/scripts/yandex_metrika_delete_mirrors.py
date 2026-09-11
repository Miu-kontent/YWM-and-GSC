import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

BASE_URL = "https://api-metrika.yandex.net"
DEFAULT_BATCH_SIZE = 50


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Ошибка чтения config.json: {e}")
        sys.exit(1)


def load_script_data():
    array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'yandex_metrika_delete_mirrors.json')
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
    url = str(url).strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def api_request(method, url, headers, json_body=None, retries=5, timeout=90):
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:500]}
            if resp.status_code in (500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2)
                continue
            return resp.status_code, body, None
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return None, None, f"Соединение не установлено после {retries} попыток"
            time.sleep(2)
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, None, f"Превышен таймаут ({timeout}с) после {retries} попыток"
            time.sleep(2)
        except Exception as e:
            return None, None, str(e)
    return None, None, "Unknown error"


def mirror_site(m):
    if isinstance(m, dict):
        return str(m.get("site") or m.get("domain") or "").strip()
    return str(m).strip()


def mirror_key(m):
    return normalize_host(mirror_site(m))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить')
        return

    metric_id = config.get('metric_id')
    if not metric_id:
        print('⚠️  Для запуска скрипта не хватает данных: metric_id')
        print('ℹ️  Получите номер счётчика кнопкой "Получить" на вкладке Яндекс → Ключи')
        return

    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        sites = [s.strip() for s in links_raw.strip().split('\n') if s.strip()]
    elif isinstance(links_raw, list):
        sites = [str(s).strip() for s in links_raw if str(s).strip()]
    else:
        sites = []

    if not sites and script_data.get('mode', 'keep') != 'keep':
        print('❌ В режиме "удалить только из списка" список сайтов не может быть пустым!')
        print('ℹ️  Введите сайты в поле выше и нажмите "Запустить" ещё раз')
        return

    mode = script_data.get('mode', 'keep')
    if mode not in ('keep', 'delete'):
        mode = 'keep'

    if not sites:
        print('ℹ️  Список пуст — в режиме "оставить только из списка" будут удалены ВСЕ зеркала счётчика (останется основной сайт)')

    headers = {"Authorization": f"OAuth {token}"}

    print(f'ℹ️  Счётчик: {metric_id}')
    print(f'ℹ️  Режим: {"оставить только из списка, остальные удалить" if mode == "keep" else "удалить только указанные в списке"}')
    print(f'ℹ️  Сайтов в списке: {len(sites)}')

    user_keys = set(normalize_host(s) for s in sites)

    print('ℹ️  Получаю зеркала счётчика...')
    status, counter_data, err = api_request('GET', f'{BASE_URL}/management/v1/counter/{metric_id}', headers)
    if err:
        print(f'⚠️  Ошибка получения данных счётчика: {err}')
        return
    if status != 200:
        error_msg = counter_data.get('message', f'HTTP {status}') if isinstance(counter_data, dict) else f'HTTP {status}'
        print(f'⚠️  Ошибка получения данных счётчика: {error_msg}')
        return

    counter = counter_data.get('counter', {}) if isinstance(counter_data, dict) else {}
    mirrors = counter.get('mirrors', []) or []
    main_site = counter.get('site', '')

    if not mirrors:
        print('ℹ️  В счётчике нет зеркал для обработки — удалять нечего')
        return

    print(f'ℹ️  Зеркал в счётчике: {len(mirrors)}')
    print(f'ℹ️  Основной сайт: {main_site or "-"} (не удаляется)')

    kept = []
    to_delete = []

    for m in mirrors:
        key = mirror_key(m)
        should_delete = (key in user_keys) if mode == 'delete' else (key not in user_keys)
        (to_delete if should_delete else kept).append(m)

    invalid_kept = [
        m for m in kept
        if any(ord(ch) > 127 for ch in mirror_site(m))
    ]
    if invalid_kept:
        print(f'ℹ️  В "оставить" есть зеркала с невалидными символами: {len(invalid_kept)}')
        print('ℹ️  Удаление определяется только списком: такие зеркала не удаляются, если не входят в область удаления')

    batch_size = script_data.get('batch_size', DEFAULT_BATCH_SIZE)
    try:
        batch_size = max(1, int(batch_size))
    except (TypeError, ValueError):
        batch_size = DEFAULT_BATCH_SIZE

    pending_deletions = list(to_delete)
    print(f'ℹ️  Останется: {len(kept)}, к удалению: {len(pending_deletions)}')
    print(f'ℹ️  Партиями по {batch_size} зеркал за запрос')

    error_count = 0
    deleted_count = 0
    stopped = False
    stop_reason = ''

    current_mirrors = list(mirrors)
    while pending_deletions:
        batch = pending_deletions[:batch_size]
        del pending_deletions[:batch_size]

        current_mirrors = [m for m in current_mirrors if m not in batch]

        print(f'🔄 Удаляю партию {len(batch)}, останется {len(current_mirrors)} зеркал...')
        put_status, put_body_data, put_err = api_request(
            'PUT',
            f'{BASE_URL}/management/v1/counter/{metric_id}',
            headers,
            json_body={"counter": {"mirrors": current_mirrors}},
            retries=5,
            timeout=90
        )
        if put_err:
            error_count += len(batch)
            stopped = True
            stop_reason = put_err
            print(f'❌ Ошибка удаления партии: {put_err}')
            for m in batch:
                print(f'__TABLE_ROW__:{json.dumps({"cells": [mirror_site(m), f"❌ {put_err}"]}, ensure_ascii=False)}')
            break
        elif put_status == 200:
            deleted_count += len(batch)
            for m in batch:
                print(f'__TABLE_ROW__:{json.dumps({"cells": [mirror_site(m), "🗑 Удален"]}, ensure_ascii=False)}')
            if pending_deletions:
                time.sleep(0.5)
        else:
            error_code = put_body_data.get('code', f'HTTP {put_status}') if isinstance(put_body_data, dict) else str(put_status)
            error_message = put_body_data.get('message', '') if isinstance(put_body_data, dict) else ''
            put_message = f"{error_message} ({error_code})" if error_message else str(error_code)
            print(f'❌ Ошибка удаления партии: {put_message}')
            error_count += len(batch)
            stopped = True
            stop_reason = put_message
            for m in batch:
                print(f'__TABLE_ROW__:{json.dumps({"cells": [mirror_site(m), f"❌ {put_message}"]}, ensure_ascii=False)}')
            break

    for d in pending_deletions:
        print(f'__TABLE_ROW__:{json.dumps({"cells": [mirror_site(d), "⏭ Не удален (остановка)"]}, ensure_ascii=False)}')

    kept_count = len(kept)
    for m in kept:
        print(f'__TABLE_ROW__:{json.dumps({"cells": [mirror_site(m), "✅ Оставлен"]}, ensure_ascii=False)}')

    print()
    print(f'ℹ️  Сверка с API после операции{" — удаление не завершено, повторите запуск для остатка" if stopped else ""}...')
    check_status, check_data, check_err = api_request('GET', f'{BASE_URL}/management/v1/counter/{metric_id}', headers)
    if not check_err and check_status == 200:
        check_counter = check_data.get('counter', {}) if isinstance(check_data, dict) else {}
        check_mirrors = check_counter.get('mirrors', []) or []
        print(f'ℹ️  Зеркал после операции: {len(check_mirrors)}')

    print()
    summary = {
        "Всего сайтов": len(mirrors),
        "Оставлено": kept_count,
        "Удалено": deleted_count,
        "Ошибок": error_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')

    if stopped:
        print()
        print(f'⚠️  Удалено {deleted_count} из {len(to_delete)}. Осталось удалить: {len(pending_deletions)}')
        print(f'ℹ️  Причина остановки: {stop_reason}')
        print('ℹ️  Запустите скрипт повторно — остаток будет удалён (список строится от текущего состояния счётчика)')


if __name__ == '__main__':
    main()