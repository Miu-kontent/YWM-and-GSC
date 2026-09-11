import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

CDP_URL = "http://127.0.0.1:9229"
BASE_URL = "https://api-metrika.yandex.net"
SETTINGS_URL = "https://metrika.yandex.ru/settings?tab=common&id={metric_id}"
AUTH_TIMEOUT = 180

SCAN_JS = """
() => {
    const items = Array.from(document.querySelectorAll('.counter-mirrors-list-item'));
    const result = [];
    for (const item of items) {
        const input = item.querySelector('input.input__control');
        const domain = input ? (input.value || '').trim() : '';
        if (!domain) continue;
        const statusEl = item.querySelector('.webmaster-status');
        let status = '';
        if (statusEl) {
            for (const cls of statusEl.classList) {
                const m = cls.match(/webmaster-status_status_(.+)/);
                if (m) status = m[1];
            }
        }
        result.push({
            domain: domain,
            status: status,
            can_create: !!item.querySelector('.webmaster-status__action_type_create'),
            can_cancel: !!item.querySelector('.webmaster-status__action_type_cancel'),
            can_repeat: !!item.querySelector('.webmaster-status__action_type_repeat')
        });
    }
    return result;
}
"""

CLICK_JS = """
(pair) => {
    const [domain, action] = pair;
    const items = Array.from(document.querySelectorAll('.counter-mirrors-list-item'));
    for (const item of items) {
        const input = item.querySelector('input.input__control');
        const d = input ? (input.value || '').trim() : '';
        if (d !== domain) continue;
        const btn = item.querySelector('.webmaster-status__action_type_' + action);
        if (!btn) return false;
        btn.scrollIntoView({behavior: 'instant', block: 'center'});
        btn.click();
        return true;
    }
    return false;
}
"""

FINAL_STATUS_LABELS = {
    "ok": "⭐ Привязан",
    "": "ℹ️ Добавлен, не привязан",
    "need_webmaster_confirm": "⚠️ Ожидает подтверждения",
    "deleted": "Откреплён",
}


def normalize_host(url):
    if not url:
        return ''
    url = url.strip()
    if '://' not in url:
        url = 'http://' + url
    parsed = urlparse(url)
    return (parsed.hostname or '').lower()


def load_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def load_script_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    arrays_dir = os.path.join(script_dir, '..', 'arrays')
    data_file = os.path.join(arrays_dir, 'yandex_metrika_bind_mirrors.json')
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def api_get_counter(metric_id, token, retries=3, timeout=15):
    headers = {'Authorization': f'OAuth {token}'}
    for attempt in range(retries):
        try:
            resp = requests.get(f'{BASE_URL}/management/v1/counter/{metric_id}', headers=headers, timeout=timeout)
            body = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
            return resp.status_code, body
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, {'message': f'Превышен таймаут ({timeout}с)'}
            time.sleep(1)
        except Exception as e:
            if attempt == retries - 1:
                return None, {'message': str(e)}
            time.sleep(1)
    return None, {}


def find_settings_frame(page):
    for frame in page.frames:
        try:
            if frame.evaluate("() => !!document.querySelector('.counter-mirrors-list__items')"):
                return frame
        except Exception:
            continue
    return None


def get_item_status(frame, domain):
    states = frame.evaluate(SCAN_JS)
    for item in states:
        if item['domain'] == domain:
            return item['status']
    return None


def wait_for_status(frame, domain, expected, timeout=15):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        status = get_item_status(frame, domain)
        last = status
        if status in expected:
            return True, status
        time.sleep(0.5)
    return False, last


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    token = config.get('oauth_token')
    metric_id = config.get('metric_id')

    if not metric_id:
        print('⚠️  Для запуска скрипта не хватает данных: metric_id')
        print('ℹ️  Получите номер счётчика кнопкой "Получить" на вкладке Яндекс → Ключи')
        return

    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить')
        return

    script_data = load_script_data()
    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        user_sites = [normalize_host(s) for s in links_raw.strip().split('\n') if s.strip()]
    elif isinstance(links_raw, list):
        user_sites = [normalize_host(s) for s in links_raw if str(s).strip()]
    else:
        user_sites = []

    print(f'ℹ️  Счётчик: {metric_id}')

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('❌ Не установлен playwright. Выполните: pip install -r requirements.txt')
        return

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(CDP_URL)
            except Exception:
                print('⚠️  Браузер не запущен или отключён порт 9229.')
                print('ℹ️  Запустите браузер кнопкой "🌐 Браузер (порт 9229)" на вкладке Яндекс и повторите.')
                return

            if not browser.contexts:
                print('❌ Не найдено ни одного контекста браузера')
                browser.close()
                return

            page = browser.contexts[0].new_page()
            page.goto(SETTINGS_URL.format(metric_id=metric_id), wait_until='domcontentloaded', timeout=60000)

            print('🔍 Ищу настройки счётчика...')
            frame = find_settings_frame(page)
            wait_start = time.time()
            if frame is None:
                print('🔐 Если браузер не авторизован — авторизуйтесь в Яндекс (может потребоваться вход в аккаунт)...')
            while frame is None and (time.time() - wait_start) < AUTH_TIMEOUT:
                time.sleep(5)
                frame = find_settings_frame(page)

            if frame is None:
                print('❌ Не удалось найти список зеркал счётчика. Проверьте авторизацию и доступ к счётчику.')
                page.close()
                browser.close()
                return

            print('✅ Настройки счётчика загружены')

            states = frame.evaluate(SCAN_JS)
            states_by_domain = {s['domain']: s for s in states}

            if user_sites:
                targets = []
                for d in user_sites:
                    if d not in states_by_domain:
                        targets.append({'domain': d, 'status': 'api_only'})
                    else:
                        targets.append({'domain': d, 'status': states_by_domain[d]['status']})
            else:
                targets = [{'domain': s['domain'], 'status': s['status']} for s in states
                           if s['status'] in ('init', 'need-webmaster-confirm', 'deleted')]
                if not targets:
                    print('✅ Все зеркала счётчика уже привязаны (нет сайтов для подключения)')

            print(f'ℹ️  Сайтов для подключения: {len(targets)}')

            pre_ok = 0
            done = 0
            pending = 0
            failed = {}

            for i, t in enumerate(targets, 1):
                domain = t['domain']
                status = t['status']
                print(f'🔄 [{i}/{len(targets)}] {domain}')

                if status == 'api_only':
                    failed[domain] = 'не найден в списке зеркал'
                    continue

                if status == 'ok':
                    pre_ok += 1
                    print('   ⭐ Уже привязан ранее')
                    continue

                if status in ('init', 'deleted'):
                    action = 'create' if status == 'init' else 'repeat'
                    ok_click = frame.evaluate(CLICK_JS, [domain, action])
                    if not ok_click:
                        failed[domain] = 'не найдена кнопка привязки'
                        continue
                    ok, final = wait_for_status(frame, domain, ['ok', 'need-webmaster-confirm'])
                    if not ok:
                        failed[domain] = f'статус не изменился (DOM: {final or "—"})'
                        continue
                    if final == 'ok':
                        done += 1
                        print('   ✔ Статус: привязан')
                    else:
                        pending += 1
                        print('   ⚠️ Запрос отправлен, ждёт подтверждения')
                    continue

                if status == 'need-webmaster-confirm':
                    ok_click = frame.evaluate(CLICK_JS, [domain, 'cancel'])
                    if not ok_click:
                        failed[domain] = 'не найдена кнопка отмены'
                        continue
                    ok, _ = wait_for_status(frame, domain, ['deleted'], timeout=10)
                    if not ok:
                        failed[domain] = 'отмена привязки не прошла'
                        continue
                    print('   ✔ Отменено, повторная привязка...')
                    ok_click = frame.evaluate(CLICK_JS, [domain, 'repeat'])
                    if not ok_click:
                        failed[domain] = 'не найдена кнопка повторной привязки'
                        continue
                    ok, final = wait_for_status(frame, domain, ['ok', 'need-webmaster-confirm'], timeout=15)
                    if not ok:
                        failed[domain] = f'после чинки статус: {final or "не изменился"}'
                        continue
                    if final == 'ok':
                        done += 1
                        print('   ✔ Статус: привязан')
                    else:
                        pending += 1
                        print('   ⚠️ Запрос отправлен, ждёт подтверждения')

            page.close()

            print()
            print('ℹ️  Проверяю финальные статусы через API...')
            status_code, data = api_get_counter(metric_id, token)

            targets_for_table = []
            if status_code == 200:
                counter = data.get('counter', {}) or {}
                mirrors2 = counter.get('mirrors2', []) or []
                api_status = {}
                for m in mirrors2:
                    if isinstance(m, dict):
                        site = (m.get('site') or m.get('domain') or '').strip().lower()
                        if site:
                            api_status[site] = m.get('status', '')
                for t in targets:
                    domain = t['domain']
                    api_val = api_status.get(domain)
                    if api_val is not None:
                        label = FINAL_STATUS_LABELS.get(api_val, f'💾 {api_val}')
                    elif domain in failed:
                        label = f'❌ {failed[domain]}'
                    else:
                        label = '—'
                    targets_for_table.append((domain, label))
            else:
                print(f'⚠️  Не удалось получить статусы: {data.get("message", f"HTTP {status_code}")}')
                for t in targets:
                    domain = t['domain']
                    label = f'❌ {failed[domain]}' if domain in failed else '—'
                    targets_for_table.append((domain, label))
            time.sleep(0.3)

            print()
            for domain, label in targets_for_table:
                print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, label]}, ensure_ascii=False)}')

            print()
            summary = {
                "Всего для подключения": len(targets),
                "Привязано ранее": pre_ok,
                "Привязано": done,
                "Ожидают подтверждения": pending,
                "Ошибок": len(failed)
            }
            print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
            print('__TABLE_DONE__:{}')

    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')


if __name__ == '__main__':
    main()