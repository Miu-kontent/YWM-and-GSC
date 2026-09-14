import json
import os
import queue
import sys
import time
import threading
import requests

from urllib.parse import urlparse

CDP_URL = "http://127.0.0.1:9229"
WEBMASTER_API = "https://api.webmaster.yandex.net/v4"
CHECKLIST_URL = "https://webmaster.yandex.ru/site/https:{domain}:443/optimization/checklist/"
CHECKLIST_LOAD_TIMEOUT = 25
API_WAIT_TIMEOUT = 120


class HostNotVerifiedError(RuntimeError):
    pass

REC_CONTAINER_SEL = "#RECOMMENDATION"
ERR_CONTAINER_SEL = ".DiagnosisChecklistErrors"
REC_SHOWALL_XPATH = '//*[@id="RECOMMENDATION"]/div/div[2]/div/div/div/button/span[2]/span'

# ======================== ИЗВЕСТНЫЕ ТИПЫ ПРОБЛЕМ ========================

PROBLEM_TYPES = {
    # --- Ошибки (FATAL / CRITICAL) ---
    'SLOW_AVG_RESPONSE_TIME': {
        'name': 'Долгий ответ сервера', 'btn': True,
        'ui_id': 'SLOW_AVG_RESPONSE_WITH_EXAMPLES',
        'xpath': '//*[@id="SLOW_AVG_RESPONSE_WITH_EXAMPLES"]/div/div[3]/button/span/span',
    },
    'DNS_ERROR': {
        'name': 'Ошибка DNS', 'btn': True,
        'xpath': '//*[@id="DNS_ERROR"]/div/div[2]/button/span/span',
    },
    'CONNECT_FAILED': {
        'name': 'Ошибка подключения', 'btn': True,
        'xpath': '//*[@id="CONNECT_FAILED"]/div/div[2]/button/span/span',
    },
    'URL_ALERT_4XX': {
        'name': 'HTTP-код 4xx', 'btn': False,
    },
    'SSL_CERTIFICATE_ERROR': {
        'name': 'Ошибка SSL-сертификата', 'btn': False,
    },
    # --- Рекомендации (POSSIBLE_PROBLEM / RECOMMENDATION) ---
    'NOT_IN_SPRAV': {
        'name': 'Яндекс Бизнес', 'btn': True,
        'ui_id': 'NO_DICTIONARY_REGIONS',
        'xpath': '//*[@id="NO_DICTIONARY_REGIONS"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'NO_REGIONS': {
        'name': 'Нет региона', 'btn': True,
        'xpath': '//*[@id="NO_REGIONS"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'DOCUMENTS_MISSING_DESCRIPTION': {
        'name': 'Метатег Description', 'btn': True,
        'xpath': '//*[@id="DOCUMENTS_MISSING_DESCRIPTION"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'DOCUMENTS_MISSING_TITLE': {
        'name': 'Метатег Title', 'btn': True,
        'xpath': '//*[@id="DOCUMENTS_MISSING_TITLE"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'FAVICON_ERROR': {
        'name': 'Файл favicon', 'btn': True,
        'ui_id': 'MISSING_FAVICON',
        'xpath': '//*[@id="MISSING_FAVICON"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'SOFT_404': {
        'name': 'Мягкие 404', 'btn': True,
        'ui_id': 'NO_404_ERRORS',
        'xpath': '//*[@id="NO_404_ERRORS"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'NOT_MOBILE_FRIENDLY': {
        'name': 'Не для мобильных', 'btn': True,
        'xpath': '//*[@id="NOT_MOBILE_FRIENDLY"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span',
    },
    'ERRORS_IN_SITEMAPS': {
        'name': 'Ошибки sitemap', 'btn': False,
    },
    'BIG_FAVICON_ABSENT': {
        'name': 'Favicon SVG/120×120', 'btn': False,
    },
    'NO_METRIKA_COUNTER_CRAWL_ENABLED': {
        'name': 'Не включён обход по счётчикам', 'btn': False,
    },
    'NO_METRIKA_COUNTER_BINDING': {
        'name': 'Метрика не привязана', 'btn': False,
    },
    'TOO_MANY_DOMAINS_ON_SEARCH': {
        'name': 'Много поддоменов', 'btn': False,
    },
    'NO_SITEMAPS': {
        'name': 'Нет используемых sitemap', 'btn': False,
    },
}

# ======================== JS СНИППЕТЫ ========================

PAGE_PROBE_JS = """
() => ({
    url: location.href,
    title: document.title || '',
    text: document.body ? document.body.innerText.slice(0, 600) : ''
})
"""

CLICK_BLOCK_HEADER_JS = """
(code) => {
    const el = document.getElementById(code);
    if (!el) return false;
    const c = el.querySelector('.Accordion-Header')
           || el.querySelector('.DiagnosisChecklistProblem')
           || el;
    c.scrollIntoView({behavior: 'instant', block: 'center'});
    c.click();
    return true;
}
"""

CLICK_CHECK_BTN_JS = """
(pair) => {
    const [code, xpath] = pair;
    const block = document.getElementById(code);
    let btn = null;

    if (xpath) {
        try {
            btn = document.evaluate(xpath, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
        } catch(e) {}
    }

    if (!btn && block) {
        btn = block.querySelector('button.DiagnosisChecklistProblemCheckButton-SubmitButton');
        if (!btn) {
            for (const b of block.querySelectorAll('button')) {
                if ((b.textContent || '').includes('Проверить')) { btn = b; break; }
            }
        }
    }

    if (!btn) {
        for (const b of document.querySelectorAll('button')) {
            if ((b.textContent || '').includes('Проверить')) { btn = b; break; }
        }
    }

    if (!btn) return {found: false, clicked: false};

    const disabled = btn.disabled
        || btn.classList.contains('g-button_disabled')
        || btn.classList.contains('disabled')
        || btn.getAttribute('aria-disabled') === 'true';

    if (disabled) return {found: true, clicked: true, already: true};

    btn.scrollIntoView({behavior: 'instant', block: 'center'});
    btn.click();
    return {found: true, clicked: true, already: false};
}
"""

CHECK_VERIFY_JS = """
(code) => {
    const block = document.getElementById(code);
    if (!block) return 'done';
    const st = block.querySelector('.DiagnosisChecklistProblemTitle-Status');
    if (st) {
        const cls = st.className || '';
        if (cls.includes('status_IN_PROGRESS') || (st.textContent || '').includes('Проверяем')) return 'done';
    }
    const btn = block.querySelector('button.DiagnosisChecklistProblemCheckButton-SubmitButton');
    if (!btn) return 'done';
    const disabled = btn.disabled
        || btn.classList.contains('g-button_disabled')
        || btn.classList.contains('disabled')
        || btn.getAttribute('aria-disabled') === 'true';
    if (disabled) return 'done';
    const hdr = block.querySelector('.Accordion-Header');
    if (hdr && !hdr.classList.contains('Accordion-Header_expanded')) return 'done';
    return 'pending';
}
"""

BLOCK_DEBUG_JS = """
(code) => {
    const block = document.getElementById(code);
    if (!block) return 'block not found';
    const st = block.querySelector('.DiagnosisChecklistProblemTitle-Status');
    const btn = block.querySelector('button.DiagnosisChecklistProblemCheckButton-SubmitButton');
    const date = block.querySelector('.DiagnosisChecklistProblemTitle-Date');
    const hdr = block.querySelector('.Accordion-Header');
    return JSON.stringify({
        status: st ? (st.textContent || '').trim() : null,
        btn: btn ? (btn.textContent || '').trim() + ' | disabled=' + (btn.disabled || btn.classList.contains('g-button_disabled')) : 'none',
        date: date ? (date.textContent || '').trim() : '',
        accordionExpanded: hdr ? hdr.classList.contains('Accordion-Header_expanded') : 'n/a'
    });
}
"""

BLOCK_STATUS_JS = """
(code) => {
    const block = document.getElementById(code);
    if (!block) return 'none';
    const st = block.querySelector('.DiagnosisChecklistProblemTitle-Status');
    if (st) {
        const cls = st.className || '';
        if (cls.includes('status_IN_PROGRESS') || /Проверяем|На проверке/i.test(st.textContent || '')) {
            return 'in_progress';
        }
    }
    return 'none';
}
"""

EXPAND_SECTION_JS = """
(pair) => {
    const [containerSel, xpath] = pair;
    if (xpath) {
        try {
            const node = document.evaluate(xpath, document, null,
                XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (node && /посмотреть все/i.test(node.textContent || '')) {
                node.click();
                return true;
            }
        } catch(e) {}
    }
    const scope = containerSel ? document.querySelector(containerSel) : document;
    const els = Array.from((scope || document).querySelectorAll('button, span, div, a'));
    const btn = els.find(el => (el.textContent || '').trim().toLowerCase() === 'посмотреть все');
    if (btn) { btn.click(); return true; }
    return false;
}
"""

SECTION_COUNT_JS = """
(selector) => {
    const c = document.querySelector(selector);
    if (!c) return 0;
    return c.querySelectorAll('div[id]').length;
}
"""


# ======================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ========================

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
    data_file = os.path.join(script_dir, '..', 'arrays', 'yandex_checklist.json')
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def api_get(url, headers, retries=3, timeout=30):
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
            time.sleep(0.5)
        except Exception as e:
            if attempt == retries - 1:
                return None, str(e), 0
            time.sleep(0.5)
    return None, "Unknown error", 0


def toast(msg, toast_type='error'):
    print(f'__TOAST__:{json.dumps({"type": toast_type, "message": str(msg)}, ensure_ascii=False)}')


def probe_reason(probe):
    url = (probe.get('url') or '').lower()
    text = ' '.join(((probe.get('text') or '') + ' ' + (probe.get('title') or '')).lower().split())
    if 'passport' in url or 'login' in url:
        return 'не выполнена авторизация в браузере'
    if 'optimization/checklist/' not in url:
        if any(m in text for m in ('не найден', 'не подтвержд', 'подтвердите', 'нет доступа', 'недостаточно прав')):
            return 'сайт не найден или не подтверждён'
        return 'открылась другая страница (сайт не подтверждён?)'
    if any(m in text for m in ('не подтвержд', 'подтвердите', 'недостаточно прав', 'нет доступа')):
        return 'сайт не подтверждён'
    return 'страница checklist не загрузилась (проверьте авторизацию)'


# ======================== API: ХОСТЫ И DIAGNOSTICS ========================

def get_hosts_map(user_id, headers):
    hosts_data, err, status = api_get(f'{WEBMASTER_API}/user/{user_id}/hosts', headers)
    if err or status != 200:
        message = (hosts_data or {}).get('message', err or f"HTTP {status}")
        return None, message
    hosts = hosts_data.get('hosts', []) or []
    result = {}
    skipped_mirrors = 0
    skipped_unverified = 0
    for h in hosts:
        if h.get('verified') is False:
            skipped_unverified += 1
            continue
        mm = h.get('main_mirror') or {}
        if mm.get('host_id') or mm.get('unicode_host_url'):
            skipped_mirrors += 1
            continue
        h_url = h.get('ascii_host_url', '') or h.get('unicode_host_url', '')
        hostname = normalize_host(h_url)
        if hostname and h.get('host_id'):
            result[hostname] = h['host_id']
    if skipped_mirrors:
        print(f'ℹ️  Пропущено зеркал: {skipped_mirrors}')
    if skipped_unverified:
        print(f'ℹ️  Пропущено неподтверждённых хостов: {skipped_unverified}')
    return result, None


def fetch_diagnostics(token, user_id, host_id, retries=3, timeout=30):
    url = f'{WEBMASTER_API}/user/{user_id}/hosts/{host_id}/diagnostics'
    headers = {"Authorization": f"OAuth {token}"}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('problems') or {}
            if resp.status_code == 429:
                time.sleep(2)
                continue
            text = resp.text or ''
            if resp.status_code == 404 and 'not verified' in text.lower():
                raise HostNotVerifiedError(f"HTTP 404: {text[:200]}")
            raise RuntimeError(f"HTTP {resp.status_code}: {text[:200]}")
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                raise
            time.sleep(0.5)
        except RuntimeError:
            raise
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(0.5)
    return {}


# ======================== BROWSER: ВЗАИМОДЕЙСТВИЕ ========================

def wait_sections(page, need_err, need_rec):
    start = time.time()
    while time.time() - start < CHECKLIST_LOAD_TIMEOUT:
        ok = True
        if need_err:
            ok = ok and bool(page.evaluate(
                "() => !!document.querySelector('.DiagnosisChecklistErrors-ErrorsContainer')"))
        if need_rec:
            ok = ok and bool(page.evaluate(
                "() => !!document.querySelector('#RECOMMENDATION .DiagnosisChecklistAccordion-Title') || !!document.querySelector('#RECOMMENDATION')"))
        if ok:
            return True
        page.wait_for_timeout(400)
    return False


def click_check_button(page, ui_id, meta):
    status = page.evaluate(BLOCK_STATUS_JS, ui_id)
    if status == 'in_progress':
        return 'in_progress'

    xpath = (meta or {}).get('xpath') or None
    page.evaluate(CLICK_BLOCK_HEADER_JS, ui_id)
    page.wait_for_timeout(500)

    for attempt in range(3):
        res = page.evaluate(CLICK_CHECK_BTN_JS, [ui_id, xpath])
        if not res.get('found'):
            return 'done' if page.evaluate(CHECK_VERIFY_JS, ui_id) == 'done' else 'unfound'
        if res.get('already'):
            return 'done'
        if not res.get('clicked'):
            page.wait_for_timeout(800)
            continue
        for _ in range(4):
            page.wait_for_timeout(1000)
            if page.evaluate(CHECK_VERIFY_JS, ui_id) == 'done':
                return 'done'
        break

    debug = page.evaluate(BLOCK_DEBUG_JS, ui_id)
    print(f'   ⚠️  Не удалось подтвердить блок {ui_id} — {debug}')
    return 'fail'


def process_section(page, section_counters, codes):
    names = []
    statuses = []
    for code in codes:
        meta = PROBLEM_TYPES.get(code)
        ui_id = (meta or {}).get('ui_id', code)

        if meta and not meta['btn']:
            names.append(f"{meta['name']} (Уведомление)")
            statuses.append('⭐ Без кнопки')
            section_counters['nobtn'] += 1
            continue

        result = click_check_button(page, ui_id, meta)

        if result == 'in_progress':
            section_counters['inprog'] += 1
            label = f"{meta['name']} (Проверка)" if meta else f"{code} (Новые данные)"
            names.append(label)
            statuses.append('⏳ На проверке')
            continue

        if meta is None:
            section_counters['new'] += 1
            if result == 'done':
                names.append(f"{code} (Новые данные)")
                statuses.append('✅ Проверено')
            elif result == 'fail':
                names.append(f"{code} (Новые данные)")
                statuses.append('❌ ошибка')
            else:
                names.append(f"{code} (Новые данные)")
                statuses.append('ℹ️ Новые данные')
        else:
            section_counters['btn'] += 1
            names.append(f"{meta['name']} (Проверка)")
            if result == 'done':
                statuses.append('✅ Проверено')
                section_counters['pressed'] += 1
            else:
                statuses.append('❌ ошибка')

    return names, statuses


# ======================== ПОТОКИ ========================

class SiteTask:
    __slots__ = (
        'domain', 'host_id', 'rec_enabled', 'err_enabled',
        'api_event', 'api_problems', 'api_err', 'host_unverified',
        'err', 'result', 'done_event',
    )
    def __init__(self, domain, host_id, rec_enabled, err_enabled):
        self.domain = domain
        self.host_id = host_id
        self.rec_enabled = rec_enabled
        self.err_enabled = err_enabled
        self.api_event = threading.Event()
        self.api_problems = None
        self.api_err = None
        self.host_unverified = False
        self.err = None
        self.result = None
        self.done_event = threading.Event()


def api_worker(task, token, user_id, host_id):
    try:
        task.api_problems = fetch_diagnostics(token, user_id, host_id)
        task.api_err = None
    except HostNotVerifiedError:
        task.host_unverified = True
        task.api_err = None
    except Exception as e:
        task.api_err = e
    finally:
        task.api_event.set()


def process_site_in_browser(page, task):
    domain = task.domain
    rec_enabled = task.rec_enabled
    err_enabled = task.err_enabled

    last_err = None
    for attempt in range(1, 4):
        try:
            page.goto(CHECKLIST_URL.format(domain=domain),
                      wait_until='domcontentloaded', timeout=60000)
            last_err = None
            break
        except Exception as e:
            last_err = e
            page.wait_for_timeout(2000)
    if last_err is not None:
        raise last_err

    if not task.api_event.wait(timeout=API_WAIT_TIMEOUT):
        raise RuntimeError('запрос diagnostics не вернулся')
    if task.api_err:
        raise task.api_err
    if task.host_unverified:
        task.result = {'empty': True}
        return

    problems = task.api_problems or {}
    rec_codes = []
    err_codes = []
    for code, pr in problems.items():
        if (pr or {}).get('state') != 'PRESENT':
            continue
        sev = pr.get('severity')
        if sev in ('FATAL', 'CRITICAL') and err_enabled:
            err_codes.append(code)
        elif sev in ('POSSIBLE_PROBLEM', 'RECOMMENDATION') and rec_enabled:
            rec_codes.append(code)

    if not rec_codes and not err_codes:
        task.result = {'empty': True}
        return

    need_err = bool(err_codes)
    need_rec = bool(rec_codes)

    if not wait_sections(page, need_err, need_rec):
        probe = page.evaluate(PAGE_PROBE_JS)
        raise RuntimeError(probe_reason(probe))
    page.wait_for_timeout(500)

    if need_err and len(err_codes) > 3:
        try:
            page.evaluate(EXPAND_SECTION_JS, [ERR_CONTAINER_SEL, None])
            page.wait_for_timeout(800)
        except Exception:
            pass

    if need_rec and len(rec_codes) > 3:
        try:
            page.evaluate(EXPAND_SECTION_JS, [REC_CONTAINER_SEL, REC_SHOWALL_XPATH])
            page.wait_for_timeout(800)
        except Exception:
            pass

    counters = {
        'rec': {'btn': 0, 'pressed': 0, 'nobtn': 0, 'new': 0, 'inprog': 0},
        'err': {'btn': 0, 'pressed': 0, 'nobtn': 0, 'new': 0, 'inprog': 0},
    }
    rec_names = rec_statuses = err_names = err_statuses = []

    if need_rec:
        rec_names, rec_statuses = process_section(page, counters['rec'], rec_codes)
    if need_err:
        err_names, err_statuses = process_section(page, counters['err'], err_codes)

    task.result = {
        'empty': False,
        'counters': counters,
        'rec': {'names': rec_names, 'statuses': rec_statuses},
        'err': {'names': err_names, 'statuses': err_statuses},
    }


def browser_worker(task_queue, stop_event):
    from playwright.sync_api import sync_playwright
    page = None
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            if not browser.contexts:
                raise RuntimeError('не найдено ни одного контекста браузера')
            context = browser.contexts[0]
            page = context.new_page()

            while not stop_event.is_set():
                task = task_queue.get()
                if task is None:
                    break
                try:
                    process_site_in_browser(page, task)
                except Exception as e:
                    task.err = e
                finally:
                    task.done_event.set()
                task_queue.task_done()
    except Exception as e:
        while True:
            try:
                task = task_queue.get_nowait()
            except Exception:
                break
            if task is None:
                break
            task.err = e
            task.done_event.set()
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass


# ======================== MAIN ========================

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    config = load_config()
    token = config.get('oauth_token')
    user_id = config.get('user_id')

    if not token:
        toast('Для запуска скрипта не хватает данных: oauth_token')
        return
    if not user_id:
        toast('Для запуска скрипта не хватает данных: user_id')
        return

    data = load_script_data()
    rec_enabled = bool(data.get('recommendations', True))
    err_enabled = bool(data.get('errors', True))

    if not rec_enabled and not err_enabled:
        toast('Выберите хотя бы один раздел: Рекомендации или Ошибки')
        return

    links_raw = data.get('links', '')
    if isinstance(links_raw, str):
        sites = [normalize_host(s) for s in links_raw.strip().split('\n') if s.strip()]
    elif isinstance(links_raw, list):
        sites = [normalize_host(s) for s in links_raw if str(s).strip()]
    else:
        sites = []

    headers = {"Authorization": f"OAuth {token}"}

    print('ℹ️  Получаю список хостов из Вебмастера...')
    hosted, err = get_hosts_map(user_id, headers)
    if err:
        print(f'⚠️  Ошибка получения хостов: {err}')
        toast(f'Ошибка получения хостов: {err}')
        return

    candidates = sites if sites else list(hosted.keys())
    if not candidates:
        toast('Нет сайтов для обработки')
        return

    total = len(candidates)

    # Проверка браузера
    try:
        from playwright.sync_api import sync_playwright as _pw_check
        with _pw_check() as _p:
            _b = _p.chromium.connect_over_cdp(CDP_URL)
            _has_ctx = bool(_b.contexts)
            _b.close()
        if not _has_ctx:
            toast('Не найдено ни одного контекста браузера')
            return
    except ImportError:
        toast('Не установлен playwright')
        return
    except Exception:
        toast('Браузер не запущен (порт 9229)')
        return

    # Счётчики
    agg = {
        'rec_btn': 0, 'rec_pressed': 0, 'rec_nobtn': 0, 'rec_new': 0, 'rec_inprog': 0,
        'err_btn': 0, 'err_pressed': 0, 'err_nobtn': 0, 'err_new': 0, 'err_inprog': 0,
    }
    unverified = 0
    script_errors = 0

    # Единый воркер браузера: одна страница на весь прогон
    task_queue = queue.Queue()
    stop_event = threading.Event()
    worker_t = threading.Thread(target=browser_worker, args=(task_queue, stop_event), daemon=True)
    worker_t.start()

    for idx, domain in enumerate(candidates, 1):
        print(f'🔄 [{idx}/{total}] {domain}')

        if domain not in hosted:
            unverified += 1
            cells = [domain]
            if rec_enabled:
                cells += ['—', '—']
            if err_enabled:
                cells += ['—', '—']
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        host_id = hosted[domain]

        task = SiteTask(domain, host_id, rec_enabled, err_enabled)
        threading.Thread(target=api_worker, args=(task, token, user_id, host_id), daemon=True).start()
        task_queue.put(task)

        if not task.done_event.wait(timeout=420):
            script_errors += 1
            cells = [domain]
            if rec_enabled:
                cells += ['—', '❌ прервано: воркер не ответил']
            if err_enabled:
                cells += ['—', '❌ прервано: воркер не ответил']
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            toast('Браузер-воркер не отвечает, прогон прерван')
            break

        if task.host_unverified:
            unverified += 1
            cells = [domain]
            if rec_enabled:
                cells += ['—', '—']
            if err_enabled:
                cells += ['—', '—']
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        if task.err:
            script_errors += 1
            reason = str(task.err)[:80]
            cells = [domain]
            if rec_enabled:
                cells += ['—', f'❌ {reason}']
            if err_enabled:
                cells += ['—', f'❌ {reason}']
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        res = task.result or {}
        if res.get('empty'):
            cells = [domain]
            if rec_enabled:
                cells += ['—', '—']
            if err_enabled:
                cells += ['—', '—']
            print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')
            continue

        counters = res.get('counters', {})
        rec = res.get('rec', {})
        err_data = res.get('err', {})

        for sec in ('rec', 'err'):
            c = counters.get(sec, {'btn': 0, 'pressed': 0, 'nobtn': 0, 'new': 0, 'inprog': 0})
            agg[f'{sec}_btn'] += c.get('btn', 0)
            agg[f'{sec}_pressed'] += c.get('pressed', 0)
            agg[f'{sec}_nobtn'] += c.get('nobtn', 0)
            agg[f'{sec}_new'] += c.get('new', 0)
            agg[f'{sec}_inprog'] += c.get('inprog', 0)

        rec_names = rec.get('names', [])
        rec_statuses = rec.get('statuses', [])
        err_names = err_data.get('names', [])
        err_statuses = err_data.get('statuses', [])

        cells = [domain]
        if rec_enabled:
            cells.append(rec_names or ['—'])
            cells.append(rec_statuses or ['—'])
        if err_enabled:
            cells.append(err_names or ['—'])
            cells.append(err_statuses or ['—'])

        print(f'__TABLE_ROW__:{json.dumps({"cells": cells}, ensure_ascii=False)}')

    stop_event.set()
    task_queue.put(None)
    worker_t.join(timeout=10)

    print()
    summary = {
        'Количество сайтов': total,
        'Не подтверждено': unverified,
        'Ошибок с проверкой': agg['err_btn'],
        'Ошибок нажато': agg['err_pressed'],
        'Ошибок без кнопки': agg['err_nobtn'],
        'Ошибок на проверке': agg['err_inprog'],
        'Рекомендаций с проверкой': agg['rec_btn'],
        'Рекомендаций нажато': agg['rec_pressed'],
        'Рекомендаций без кнопки': agg['rec_nobtn'],
        'Рекомендаций на проверке': agg['rec_inprog'],
        'Новых': agg['rec_new'] + agg['err_new'],
        'Ошибок скрипта': script_errors,
    }
    print(f'__SUMMARY__:{json.dumps(summary, ensure_ascii=False)}')
    print('__TABLE_DONE__:{}')


if __name__ == '__main__':
    main()
