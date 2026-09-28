"""
Добавление сайтов (зеркал) в счётчик Метрики.

Диагностика ошибок PUT: подробная телеметрия уходит в консоль разработчика GUI
по протоколу __DEBUG__ (F12). В статусную строку, лог и таблицу причина ошибки
НЕ выводится — только факт неудачи.

Классификация ответов API:
  ok        — 2xx
  retryable — 500/502/503/504, Timeout, ConnectionError (ретраи внутри api_request)
  fatal     — 400/403/404/406/409 (повтор тем же телом бессмысленен → делим пачку)
  quota     — 429 (по error_type: суточный лимит → стоп, лимит по IP → пауза)

Размер пачки подстраивается: не прошедший размер помечается «плохим» и больше
не пробуется в этом прогоне, после успеха размер наращивается вдвое (не выше 50).
"""

import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

# Телеметрия в консоль разработчика (__DEBUG__). В интерфейс не выводится.
DEBUG_TELEMETRY = True
# Подряд идущие неустранимые ошибки на пачке из 1 → остановка прогона
MAX_CONSECUTIVE_FAILURES = 3
# Сколько раз ждать при лимите запросов по IP перед остановкой
MAX_IP_QUOTA_WAITS = 3

BASE_URL = "https://api-metrika.yandex.net"
DEFAULT_BATCH_SIZE = 50

RETRYABLE_STATUS = (500, 502, 503, 504)
FATAL_STATUS = (400, 403, 404, 406, 409)
RETRY_BACKOFF = 2
API_RETRIES = 5
API_TIMEOUT = 90
BODY_CUT = 800


def dbg(tag, msg, **fields):
    """Техническая телеметрия → консоль разработчика GUI (протокол __DEBUG__)."""
    if not DEBUG_TELEMETRY:
        return
    payload = {"tag": tag, "msg": msg}
    payload.update(fields)
    try:
        print(f'__DEBUG__:{json.dumps(payload, ensure_ascii=False)}', flush=True)
    except Exception:
        pass


def toast(message, type_='error'):
    print(f'__TOAST__:{json.dumps({"type": type_, "message": message}, ensure_ascii=False)}', flush=True)


def load_script_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    arrays_dir = os.path.join(script_dir, '..', 'arrays')
    data_file = os.path.join(arrays_dir, 'yandex_metrika_add_mirrors.json')
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


from yandex_client import load_config


def normalize_host(url):
    if not url:
        return ''
    url = str(url).strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def classify(status, err):
    """(status, err) → kind: ok | retryable | fatal | quota."""
    if err is not None or status is None:
        return 'retryable'
    if 200 <= status < 300:
        return 'ok'
    if status == 429:
        return 'quota'
    if status in RETRYABLE_STATUS:
        return 'retryable'
    return 'fatal'


def api_error_type(body):
    if not isinstance(body, dict):
        return ''
    errors = body.get('errors')
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return str(first.get('error_type') or '')
    return ''


def error_detail(status, body, err):
    """Причина ошибки — только для консоли разработчика и debug-контекста."""
    if err:
        return err
    if not isinstance(body, dict):
        return f'HTTP {status}'
    message = body.get('message') or ''
    etype = api_error_type(body)
    code = body.get('code', status)
    parts = [p for p in (etype, message) if p]
    detail = ' '.join(parts) if parts else f'HTTP {code}'
    return f'{detail} (код {code})'


def api_request(method, url, headers, json_body=None, retries=API_RETRIES, timeout=API_TIMEOUT,
                mirrors_count=None, batch_size=None, note=None):
    """Запрос к API Метрики с телеметрией. Возвращает (status, body, err, kind)."""
    body_bytes = len(json.dumps(json_body, ensure_ascii=False).encode('utf-8')) if json_body is not None else 0
    common = {
        'method': method,
        'mirrors': mirrors_count,
        'batch': batch_size,
        'body_kb': round(body_bytes / 1024, 1),
    }
    if note:
        common['note'] = note

    status, body, err = None, None, None
    for attempt in range(1, retries + 1):
        started = time.time()
        status, body, err = None, None, None
        exc_name = ''
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            status = resp.status_code
            try:
                body = resp.json()
            except Exception:
                body = {"raw": resp.text[:BODY_CUT]}
        except requests.exceptions.Timeout as e:
            err = f'Таймаут {timeout}с'
            exc_name = type(e).__name__
        except requests.exceptions.ConnectionError:
            err = 'Соединение не установлено'
            exc_name = type(e).__name__
        except Exception as e:
            err = str(e) or type(e).__name__
            exc_name = type(e).__name__

        elapsed = round(time.time() - started, 2)
        kind = classify(status, err)

        fields = dict(common)
        fields.update({
            'attempt': f'{attempt}/{retries}',
            'elapsed': elapsed,
            'status': status,
            'kind': kind,
        })
        if exc_name:
            fields['exception'] = exc_name
        if err:
            fields['error'] = err
        if kind in ('fatal', 'quota'):
            fields['error_type'] = api_error_type(body)
            fields['detail'] = error_detail(status, body, err)
            fields['response'] = json.dumps(body, ensure_ascii=False)[:BODY_CUT]
        dbg('API', f'{method} → {status if status is not None else "нет ответа"} за {elapsed}с ({kind})', **fields)

        if kind != 'retryable':
            return status, body, err, kind
        if attempt < retries:
            dbg('RETRY', f'повтор через {RETRY_BACKOFF}с: {error_detail(status, body, err)}')
            time.sleep(RETRY_BACKOFF)

    return status, body, err, classify(status, err)


def fetch_counter(metric_id, headers):
    """GET счётчика → (ok, mirrors, mirrors2, detail)."""
    status, body, err, _kind = api_request(
        'GET',
        f'{BASE_URL}/management/v1/counter/{metric_id}',
        headers,
        note='чтение счётчика'
    )
    if err or status != 200:
        return False, [], [], error_detail(status, body, err)
    counter = body.get('counter', {}) if isinstance(body, dict) else {}
    return True, counter.get('mirrors', []) or [], counter.get('mirrors2', []) or [], ''


def mirror_key(m):
    if isinstance(m, dict):
        return (m.get("site") or m.get("domain") or "").strip().lower()
    return str(m).strip().lower()


def mirror_status(m):
    if isinstance(m, dict):
        return m.get("status", "")
    return ""


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    script_data = load_script_data()

    token = config.get('oauth_token')
    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Авторизуйте аккаунт на вкладке Яндекс → Ключи')
        return

    metric_id = config.get('metric_id')
    if not metric_id:
        print('⚠️  Для запуска скрипта не хватает данных: metric_id')
        print('ℹ️  Получите номер счётчика кнопкой "Получить" на вкладке Яндекс → Ключи')
        return

    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        sites = [l.strip() for l in links_raw.strip().split('\n') if l.strip()]
    elif isinstance(links_raw, list):
        sites = [str(l).strip() for l in links_raw if str(l).strip()]
    else:
        sites = []

    if not sites:
        print('❌ Нет сайтов для добавления!')
        return

    headers = {
        'Authorization': f'OAuth {token}'
    }

    dbg('SCRIPT', 'старт добавления зеркал', counter=metric_id, sites=len(sites))

    print(f'ℹ️  Счётчик: {metric_id}')
    print(f'ℹ️  Сайтов к добавлению: {len(sites)}')

    print(f'ℹ️  Получаю зеркала счётчика...')
    ok, mirrors, mirrors2, detail = fetch_counter(metric_id, headers)
    if not ok:
        print('⚠️  Ошибка получения данных счётчика')
        dbg('ERROR', 'GET счётчика не удался', detail=detail)
        toast(f'Не удалось получить данные счётчика {metric_id}. Подробности — в консоли разработчика (F12)')
        return

    dbg('SCRIPT', 'счётчик получен', mirrors=len(mirrors), mirrors2=len(mirrors2))

    existing_status = {}
    for m in mirrors2:
        key = mirror_key(m)
        if key:
            existing_status[key] = mirror_status(m)
    for m in mirrors:
        key = mirror_key(m)
        if key and key not in existing_status:
            existing_status[key] = ""

    active_mirrors = list(mirrors)

    def build_mirror_item(site):
        if active_mirrors and isinstance(active_mirrors[0], dict):
            return {"site": site}
        return site

    already_count = 0
    added_count = 0
    error_count = 0

    pending_additions = []
    for site in sites:
        hostname = normalize_host(site)
        if hostname in existing_status:
            status_label = existing_status[hostname]
            status_map = {
                "": "✅ Добавлен ранее",
                "need_webmaster_confirm": "⚠️ Ожидает подтверждения",
                "ok": "⭐ Привязан ранее",
            }
            row_status = status_map.get(status_label, f"ℹ️ Уже добавлено ({status_label})")
            already_count += 1
            print(f'__TABLE_ROW__:{json.dumps({"cells": [site, row_status]}, ensure_ascii=False)}')
            continue
        pending_additions.append(hostname)

    if not pending_additions:
        print()
        summary = {
            "Всего": len(sites),
            "Добавлено ранее": already_count,
            "Добавлено": 0,
            "Ошибок": 0
        }
        print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
        print('__TABLE_DONE__:{}')
        return

    batch_size = DEFAULT_BATCH_SIZE
    processed = 0
    total = len(pending_additions)
    i = 0
    stopped = False
    stop_reason = ''   # полная причина — только в консоль (__DEBUG__)
    stop_brief = ''    # короткая формулировка для тоста, без текста ошибки API
    consecutive_failures = 0
    ip_waits = 0
    bad_batches = set()   # размеры пачек, которые уже признаны нерабочими в этом прогоне

    print(f'ℹ️  Список новых сайтов: {len(pending_additions)}')
    print(f'ℹ️  Пакетная вставка (по {batch_size}, с авто-уменьшением при ошибках)...')

    def safe_batch_size(size):
        """Не возвращаемся к размеру пачки, который уже не проходил в этом прогоне."""
        while size > 1 and size in bad_batches:
            size = max(1, size // 2)
        return size

    def put_batch(batch, note='вставка пачки'):
        dbg('PUT', f'тело PUT: зеркал в счётчике={len(active_mirrors)}, новых={len(batch)}',
            new_sample=batch[:10], new_total=len(batch), note=note)
        put_body = {"counter": {"mirrors": active_mirrors + [build_mirror_item(s) for s in batch]}}
        result = api_request(
            'PUT',
            f'{BASE_URL}/management/v1/counter/{metric_id}',
            headers,
            json_body=put_body,
            mirrors_count=len(active_mirrors),
            batch_size=len(batch),
            note=note
        )
        return result, put_body

    def refresh_mirrors(reason):
        """Перечитываем зеркала: список мог устареть (параллельные правки счётчика)."""
        ok, new_mirrors, new_mirrors2, detail = fetch_counter(metric_id, headers)
        if not ok:
            dbg('ERROR', 'не удалось перечитать зеркала', reason=reason, detail=detail)
            return False
        before = len(active_mirrors)
        active_mirrors.clear()
        active_mirrors.extend(new_mirrors)
        dbg('SYNC', f'зеркала перечитаны ({reason})', before=before, after=len(active_mirrors),
            mirrors2=len(new_mirrors2))
        return True

    while i < len(pending_additions):
        batch_size = safe_batch_size(batch_size)
        batch = pending_additions[i:i + batch_size]

        print(f'🔄 [{processed}/{total}] Добавляю партию {len(batch)}, батч-размер {batch_size}...')
        (put_status, put_body_data, put_err, kind), put_body = put_batch(batch)
        detail = error_detail(put_status, put_body_data, put_err)

        if kind == 'ok':
            active_mirrors.clear()
            active_mirrors.extend(put_body["counter"]["mirrors"])
            consecutive_failures = 0
            for s in batch:
                existing_status[s] = ""
                added_count += 1
                processed += 1
                print(f'__TABLE_ROW__:{json.dumps({"cells": [s, "✅ Добавлен"]}, ensure_ascii=False)}')
            i += len(batch)
            # пачка такого размера прошла — пробуем крупнее, но не возвращаемся к заведомо плохому размеру
            batch_size = safe_batch_size(min(DEFAULT_BATCH_SIZE, max(1, len(batch) * 2)))
            continue

        if kind == 'quota':
            etype = api_error_type(put_body_data)
            if etype == 'quota_requests_by_ip' and ip_waits < MAX_IP_QUOTA_WAITS:
                ip_waits += 1
                dbg('QUOTA', 'лимит запросов по IP — пауза 5с', wait=ip_waits, detail=detail)
                print('⏳  Лимит запросов к API, пауза 5 секунд...')
                time.sleep(5)
                refresh_mirrors('после паузы по квоте')
                continue
            stop_reason = f'исчерпан лимит запросов API ({etype or "429"}): {detail}'
            stop_brief = 'исчерпан лимит запросов к API'
            dbg('QUOTA', 'квота исчерпана — остановка', error_type=etype, detail=detail,
                batch=len(batch), mirrors=len(active_mirrors))
            stopped = True
            break

        # fatal (4xx) или retryable, исчерпавший ретраи — делим пачку
        if len(batch) > 1:
            half = max(1, len(batch) // 2)
            bad_batches.add(len(batch))
            dbg('SPLIT', f'пачка {len(batch)} не прошла ({kind}) → делю пополам',
                detail=detail, new_batch=half, mirrors=len(active_mirrors))
            print(f'⚠️  Пачка {len(batch)} не прошла, уменьшаю пакет до {half}...')
            batch_size = safe_batch_size(half)
            if kind == 'retryable':
                # PUT мог примениться на сервере, а ответ не дошёл — список устарел
                refresh_mirrors('после неуспешного PUT')
            continue

        # пачка из 1 — делить нечего
        consecutive_failures += 1
        error_count += 1
        processed += 1
        dbg('FAIL', f'ошибка на пачке из 1 ({kind})', site=batch[0], detail=detail,
            consecutive=consecutive_failures, mirrors=len(active_mirrors))
        print(f'__TABLE_ROW__:{json.dumps({"cells": [batch[0], "❌ Ошибка"]}, ensure_ascii=False)}')
        i += 1
        batch_size = safe_batch_size(DEFAULT_BATCH_SIZE)
        refresh_mirrors('после ошибки на пачке из 1')

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            stop_reason = f'{consecutive_failures} ошибки подряд, последняя: {detail}'
            stop_brief = f'{consecutive_failures} ошибки подряд на пачке из 1'
            stopped = True
            break

    for rest in pending_additions[i:]:
        print(f'__TABLE_ROW__:{json.dumps({"cells": [rest, "⏭ Не обработан (остановка)"]}, ensure_ascii=False)}')

    ok, final_mirrors, _, _ = fetch_counter(metric_id, headers)
    if ok:
        dbg('SYNC', 'сверка после операции', mirrors=len(final_mirrors))
        print(f'ℹ️  Зеркал в счётчике после операции: {len(final_mirrors)}')

    if stopped:
        dbg('STOP', 'прогон остановлен', reason=stop_reason, processed=processed, total=total)

    print()
    summary = {
        "Всего": len(sites),
        "Добавлено ранее": already_count,
        "Добавлено": added_count,
        "Ошибок": error_count
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')

    if stopped:
        print(f'⚠️  Остановлено: обработано {processed} из {total}, добавлено {added_count}')
        toast(f'Скрипт остановлен: {stop_brief or "прервано"}. Подробности — в консоли разработчика (F12)')


if __name__ == '__main__':
    main()
