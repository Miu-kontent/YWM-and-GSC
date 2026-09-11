import json
import os
import sys
import time
import requests

from urllib.parse import urlparse

CDP_URL = "http://127.0.0.1:9229"
WEBMASTER_API = "https://api.webmaster.yandex.net/v4"
REGIONS_URL = "https://webmaster.yandex.ru/site/https:{domain}:443/serp-snippets/regions/"
AUTH_TIMEOUT = 180

STATE_SCAN_JS = """
() => {
    const item = document.querySelector('ul.RegionsList.RegionsList_multiline li.RegionsList-Item');
    const current = item ? (item.textContent || '').trim() : '';
    return {
        currentRegion: current,
        hasChangeRegions: !!document.querySelector('.ChangeRegions'),
        hasAddContainer: !!document.querySelector('.AddRegionContainer'),
        hasSelected: !!document.querySelector('.AddRegionContainer_selected')
    };
}
"""

CLICK_BY_TEXT_JS = """
(text) => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const btn = buttons.find(b =>
        !b.disabled && !b.classList.contains('g-button_disabled') && (b.textContent || '').includes(text)
    );
    if (!btn) return false;
    btn.scrollIntoView({behavior: 'instant', block: 'center'});
    btn.click();
    return true;
}
"""

FILL_INPUT_JS = """
(pair) => {
    const [selector, text] = pair;
    const input = document.querySelector(selector);
    if (!input) return false;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, text);
    input.dispatchEvent(new Event('input', {bubbles: true}));
    return true;
}
"""

SUGGEST_ITEMS_JS = """
() => Array.from(document.querySelectorAll('.WmSuggest-Item')).map(e => (e.textContent || '').trim())
"""

SELECT_SUGGEST_JS = """
(index) => {
    const items = Array.from(document.querySelectorAll('.WmSuggest-Item'));
    if (index < 0 || index >= items.length) return false;
    const target = items[index].closest('[role="option"]') || items[index];
    target.scrollIntoView({behavior: 'instant', block: 'center'});
    target.click();
    return true;
}
"""

SAVE_ENABLED_JS = """
() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b =>
        (b.textContent || '').includes('Сохранить') && !b.disabled && !b.classList.contains('g-button_disabled')
    );
    return !!btn;
}
"""

CLEAR_SELECTED_JS = """
() => {
    const btn = document.querySelector('.WmSuggestSingle-CloseButton');
    if (!btn) return false;
    btn.click();
    return true;
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
    data_file = os.path.join(arrays_dir, 'yandex_region_add.json')
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


def wait_selector(page, selector, timeout=8):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_selector(selector, timeout=int(timeout * 1000))
        return True
    except PlaywrightTimeout:
        return False


def wait_until(page, js, timeout=8, expected=None):
    start = time.time()
    last = None
    while time.time() - start < timeout:
        try:
            last = page.evaluate(js)
        except Exception:
            last = None
        if expected is not None:
            if last == expected:
                return True, last
        elif last:
            return True, last
        time.sleep(0.5)
    return False, last


def match_suggest_index(items, city):
    target = city.strip().lower()
    if not target:
        return -1
    for i, text in enumerate(items):
        t = text.lower()
        if t.startswith(target):
            return i
    for i, text in enumerate(items):
        if target in text.lower():
            return i
    return -1


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    token = config.get('oauth_token')
    user_id = config.get('user_id')
    contact_path = (config.get('contact_path') or '').strip().strip('/')

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
        sites = [normalize_host(s) for s in links_raw.strip().split('\n') if s.strip()]
    elif isinstance(links_raw, list):
        sites = [normalize_host(s) for s in links_raw if str(s).strip()]
    else:
        sites = []

    city_raw = script_data.get('city', '')
    if isinstance(city_raw, str):
        cities = [c.strip() for c in city_raw.strip().split('\n') if c.strip()]
    elif isinstance(city_raw, list):
        cities = [str(c).strip() for c in city_raw if str(c).strip()]
    else:
        cities = []

    mode = 'add' if sites else 'check'

    if mode == 'add':
        if not contact_path:
            print('⚠️  Для запуска скрипта не хватает данных: contact_path')
            print('ℹ️  Заполните поле «Путь контактов» в конфиге Яндекс-раздела')
            return
        if len(sites) != len(cities):
            print(f'❌ Размеры списков не совпадают: сайтов {len(sites)}, городов {len(cities)}')
            print('ℹ️  Каждый сайт должен соответствовать городу в той же строке')
            return
        print(f'ℹ️  Режим: добавление региона')
        print(f'ℹ️  Сайтов: {len(sites)}')
        print(f'ℹ️  Путь контактов: /{contact_path}/')
    else:
        headers = {"Authorization": f"OAuth {token}"}
        print('ℹ️  Режим: проверка регионов (списки пусты)')
        print('ℹ️  Получаю все сайты из Вебмастера...')
        sites, err = get_all_hosts(user_id, headers)
        if err:
            print(f'⚠️  Ошибка получения сайтов: {err}')
            return
        print(f'ℹ️  Сайтов в Вебмастере: {len(sites)}')

    if not sites:
        print('❌ Нет сайтов для обработки!')
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('❌ Не установлен playwright.')
        return

    total = len(sites)
    processed = 0
    failed_count = 0

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

            for i, domain in enumerate(sites, 1):
                city = cities[i - 1] if mode == 'add' else ''
                contact_url = f'https://{domain}/{contact_path}/' if mode == 'add' else '-'
                print(f'🔄 [{i}/{total}] {domain}')

                page = browser.contexts[0].new_page()
                try:
                    last_err = None
                    for attempt in range(1, 4):
                        try:
                            page.goto(REGIONS_URL.format(domain=domain), wait_until='domcontentloaded', timeout=60000)
                            last_err = None
                            break
                        except Exception as e:
                            last_err = e
                            print(f'⚠️  [{domain}] Попытка {attempt}/3: ошибка загрузки, жду 3с...')
                            time.sleep(3)

                    if last_err is not None:
                        raise last_err

                    if not wait_selector(page, '.RegionsContent', timeout=AUTH_TIMEOUT):
                        raise RuntimeError('страница региона не загрузилась (проверьте авторизацию)')

                    state = page.evaluate(STATE_SCAN_JS)

                    if mode == 'check':
                        current = state.get('currentRegion', '')
                        if not current or 'не задан' in current:
                            status = 'Нет региона'
                        else:
                            status = f'✅ Регион: {current}'
                        processed += 1
                        print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, current or "-", "-", status]}, ensure_ascii=False)}')
                        continue

                    # ---- режим добавления ----
                    if not state.get('hasChangeRegions'):
                        clicked = page.evaluate(CLICK_BY_TEXT_JS, 'Добавить регион')
                        if not clicked:
                            clicked = page.evaluate(CLICK_BY_TEXT_JS, 'Изменить регион')
                        ok, _ = wait_until(page, "() => !!document.querySelector('.ChangeRegions')", timeout=6)
                        if not clicked or not ok:
                            raise RuntimeError('не удалось открыть панель изменения региона')

                    if not state.get('hasAddContainer'):
                        clicked = page.evaluate(CLICK_BY_TEXT_JS, 'Добавить регион')
                        ok, _ = wait_until(page, "() => !!document.querySelector('.AddRegionContainer')", timeout=6)
                        if not clicked or not ok:
                            raise RuntimeError('не удалось открыть поле выбора региона')

                    state = page.evaluate(STATE_SCAN_JS)
                    if state.get('hasSelected'):
                        page.evaluate(CLEAR_SELECTED_JS)
                        time.sleep(0.5)

                    ok_fill = page.evaluate(FILL_INPUT_JS, ['input#suggest-1', city])
                    if not ok_fill:
                        raise RuntimeError('поле ввода региона не найдено')

                    ok_items, _ = wait_until(page, SUGGEST_ITEMS_JS, timeout=8)
                    if not ok_items:
                        raise RuntimeError('город не найден в подсказках')

                    items = page.evaluate(SUGGEST_ITEMS_JS)
                    idx = match_suggest_index(items, city)
                    if idx < 0:
                        raise RuntimeError(f'город «{city}» не найден в списке подсказок')

                    clicked = page.evaluate(SELECT_SUGGEST_JS, idx)
                    ok_sel, _ = wait_until(page, "() => !!document.querySelector('.AddRegionContainer_selected')", timeout=6)
                    if not clicked or not ok_sel:
                        raise RuntimeError('не удалось выбрать город из списка')

                    ok_link = page.evaluate(FILL_INPUT_JS, ['.ChangeRegions-InfoLink input[type="url"]', contact_url])
                    if not ok_link:
                        raise RuntimeError('поле ссылки контактов не найдено')

                    ok_save, _ = wait_until(page, SAVE_ENABLED_JS, timeout=6)
                    if not ok_save:
                        raise RuntimeError('кнопка «Сохранить» не стала доступной')

                    page.evaluate(CLICK_BY_TEXT_JS, 'Сохранить')
                    ok_closed, _ = wait_until(page, "() => !document.querySelector('.ChangeRegions')", timeout=15)
                    if not ok_closed:
                        raise RuntimeError('сохранение региона не завершилось')

                    processed += 1
                    print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, city, contact_url, "⏳ Отправлено на проверку"]}, ensure_ascii=False)}')

                except Exception as e:
                    failed_count += 1
                    reason = str(e)[:90]
                    print(f'__TABLE_ROW__:{json.dumps({"cells": [domain, city or "-", contact_url, f"❌ {reason}"]}, ensure_ascii=False)}')
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
                    time.sleep(0.5)

    except Exception as e:
        print(f'❌ Критическая ошибка: {e}')

    finally:
        print()
        summary = {
            "Сайтов": total,
            "Путь контактов": f'/{contact_path}/' if contact_path else '-',
            "Успешно": processed,
            "Ошибок": failed_count
        }
        print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
        print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()