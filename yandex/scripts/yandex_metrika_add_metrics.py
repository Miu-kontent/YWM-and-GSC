import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

CDP_URL = "http://127.0.0.1:9229"
WEBMASTER_API = "https://api.webmaster.yandex.net/v4"
CRUMB_URL = "https://webmaster.yandex.ru/site/https:{domain}:443/indexing/crawl-metrika/"
AUTH_TIMEOUT = 180

SCAN_JS = """
() => {
    const input = document.querySelector('input.g-switch__control[role="switch"]');
    if (!input) return {found: false, state: 'not_found'};
    const label = input.closest('label.g-switch');
    const state = (label && label.classList.contains('g-switch_checked')) || input.checked;
    return {found: true, state: state ? 'enabled' : 'disabled'};
}
"""

CLICK_JS = """
() => {
    const input = document.querySelector('input.g-switch__control[role="switch"]');
    if (!input) return false;
    let target = null;
    for (const sel of ['label.g-switch', '.g-control-label__indicator', '.g-switch__indicator']) {
        target = input.closest(sel);
        if (target) break;
    }
    if (!target) target = input;
    target.click();
    return true;
}
"""

SCROLL_JS = """
() => {
    const container = document.querySelector('.ScrollableContainer-Wrapper');
    if (container) {
        container.scrollLeft = container.scrollWidth;
        return true;
    }
    return false;
}
"""


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
    data_file = os.path.join(arrays_dir, 'yandex_metrika_add_metrics.json')
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def api_get(url, headers, retries=3, timeout=15):
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            try:
                return resp.json(), None, resp.status_code
            except Exception:
                return None, f"не JSON: {resp.text[:300]}", resp.status_code
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return None, f'Превышен таймаут ({timeout}с)', 0
            time.sleep(1)
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e), 0
            time.sleep(1)
    return None, "Unknown error", 0


def scan_state(page):
    return page.evaluate(SCAN_JS)


def wait_for_switch(page, timeout=9):
    start = time.time()
    while time.time() - start < timeout:
        res = scan_state(page)
        if res.get('found'):
            return res
        time.sleep(1.5)
    return res


def wait_for_state(page, target, timeout=15):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        res = scan_state(page)
        last = res.get('state', 'not_found')
        if last == target:
            return True, last
        time.sleep(1.5)
    return False, last


def get_all_hosts(user_id, headers):
    hosts_data, err, status = api_get(f'{WEBMASTER_API}/user/{user_id}/hosts', headers)
    if err or status != 200:
        message = (hosts_data or {}).get('message', err or f"HTTP {status}")
        return None, message
    hosts = hosts_data.get('hosts', []) or []

    def is_mirror(h):
        mm = h.get('main_mirror') or {}
        return bool(mm.get('host_id') or mm.get('unicode_host_url'))

    skipped = [h for h in hosts if is_mirror(h)]
    if skipped:
        print(f'ℹ️  Пропущено зеркал: {len(skipped)}')

    domains = []
    for h in hosts:
        if is_mirror(h):
            continue
        h_url = h.get('ascii_host_url', '') or h.get('unicode_host_url', '')
        hostname = normalize_host(h_url)
        if hostname:
            domains.append(hostname)
    return domains, None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    token = config.get('oauth_token')
    user_id = config.get('user_id')

    if not token:
        print('⚠️  Для запуска скрипта не хватает данных: oauth_token')
        print('ℹ️  Получите токен на вкладке Яндекс → Ключи → Получить')
        return

    if not user_id:
        print('⚠️  Для запуска скрипта не хватает данных: user_id')
        print('ℹ️  Получите user_id на вкладке Яндекс → Ключи → Получить')
        return

    script_data = load_script_data()
    links_raw = script_data.get('links', '')
    if isinstance(links_raw, str):
        user_sites = [normalize_host(s) for s in links_raw.strip().split('\n') if s.strip()]
    elif isinstance(links_raw, list):
        user_sites = [normalize_host(s) for s in links_raw if str(s).strip()]
    else:
        user_sites = []

    headers = {"Authorization": f"OAuth {token}"}

    if user_sites:
        domains = user_sites
        print(f'ℹ️  Сайтов из списка: {len(domains)}')
    else:
        print('ℹ️  Список пуст — получаю все сайты из Вебмастера...')
        domains, err = get_all_hosts(user_id, headers)
        if err:
            print(f'⚠️  Ошибка получения сайтов: {err}')
            return
        print(f'ℹ️  Сайтов в Вебмастере: {len(domains)}')

    if not domains:
        print('❌ Нет сайтов для обработки!')
        return

    already = 0
    enabled = 0
    failed = {}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('❌ Не установлен playwright.')
        return

    total = len(domains)

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

            for i, domain in enumerate(domains, 1):
                print(f'🔄 [{i}/{total}] {domain}')

                try:
                    page = browser.contexts[0].new_page()

                    last_err = None
                    for attempt in range(1, 4):
                        try:
                            page.goto(CRUMB_URL.format(domain=domain), wait_until='domcontentloaded', timeout=60000)
                            last_err = None
                            break
                        except Exception as e:
                            last_err = e
                            print(f'⚠️  [{domain}] Попытка {attempt}/3: ошибка загрузки, жду 3с...')
                            time.sleep(3)

                    if last_err is not None:
                        raise last_err

                    res = wait_for_switch(page)
                    if not res.get('found'):
                        page.close()
                        failed[domain] = 'не найден тумблер'
                        print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, "❌ Не найден тумблер"]}, ensure_ascii=False)}')
                        continue

                    state = res.get('state', 'not_found')

                    if state == 'enabled':
                        already += 1
                        print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, "⭐ Включено ранее"]}, ensure_ascii=False)}')
                        page.close()
                        time.sleep(0.3)
                        continue

                    clicked = page.evaluate(CLICK_JS)
                    if not clicked:
                        page.close()
                        failed[domain] = 'не удалось нажать переключатель'
                        print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, "❌ Не удалось нажать"]}, ensure_ascii=False)}')
                        continue

                    ok, final = wait_for_state(page, 'enabled')
                    if ok:
                        enabled += 1
                        print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, "✅ Включено"]}, ensure_ascii=False)}')
                    else:
                        failed[domain] = f'не переключилось ({final})'
                        print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, f"❌ Не включилось ({final})"]}, ensure_ascii=False)}')

                    page.close()
                except Exception as e:
                    try:
                        page.close()
                    except Exception:
                        pass
                    failed[domain] = f'ошибка: {str(e)[:80]}'
                    print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, f"❌ {failed[domain]}"]}, ensure_ascii=False)}')
                    time.sleep(0.3)

    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')

    finally:
        print()
        summary = {
            "Всего сайтов": total,
            "Включено ранее": already,
            "Включено": enabled,
            "Не включено": len(failed)
        }
        print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
        print('__TABLE_DONE__:{}')

        if failed:
            print()
            print('ℹ️  Проблемные сайты:')
            for d, reason in failed.items():
                print(f'ℹ️  • {d} — {reason}')


if __name__ == '__main__':
    main()