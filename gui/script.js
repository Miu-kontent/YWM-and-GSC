let runningScripts = {};

function onDOMReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}

window.addEventListener('pywebviewready', () => {
    onDOMReady(async () => {
        await applySavedTheme();
        const loaderStatus = document.getElementById('loader-status');
        const loader = document.getElementById('loader');
        const versionOverlay = document.getElementById('version-overlay');

        loaderStatus.innerText = "Проверка обновлений...";
        try {
            const updateCheck = await window.pywebview.api.check_updates();
            const verLabel = document.getElementById('launcher-version');
            if (verLabel) verLabel.innerText = `v${updateCheck.local_version}`;

            if (updateCheck.success) {
                if (updateCheck.update_available) {
                    addLoaderLog(`⚠️ Доступна версия ${updateCheck.remote_version}`);
                    document.getElementById('local-ver').textContent = updateCheck.local_version;
                    document.getElementById('remote-ver').textContent = updateCheck.remote_version;
                    setTimeout(() => { versionOverlay.classList.remove('hidden'); }, 500);
                } else {
                    addLoaderLog(`✅ Версия актуальна (${updateCheck.local_version})`);
                    setTimeout(() => { loader.classList.add('hidden'); }, 500);
                }
            } else {
                addLoaderLog(`⚠️ Не удалось проверить обновления (error_code: ${updateCheck.error_code})`);
                setTimeout(() => { loader.classList.add('hidden'); }, 500);
            }
        } catch (err) {
            addLoaderLog(`⚠️ Не удалось проверить обновления: ${err.message}`);
            setTimeout(() => { loader.classList.add('hidden'); }, 500);
        }

        loaderStatus.innerText = "Загрузка данных...";
        addLoaderLog(`ℹ️ Загрузка ключей ...`);
        await loadGlobalKeys();
        addLoaderLog(`ℹ️ Загрузка скриптов ...`);
        await loadScriptsLists();
    })
});

async function doUpdate() {
    const versionOverlay = document.getElementById('version-overlay');
    const loaderStatus = document.getElementById('loader-status');

    if (versionOverlay) versionOverlay.classList.add('hidden');
    if (loaderStatus) loaderStatus.innerText = "Скачивание и установка обновления...";

    const res = await window.pywebview.api.update_app();

    if (res && res.success) {
        if (loaderStatus) loaderStatus.innerText = "Обновление установлено! Перезапуск...";
        setTimeout(() => {
            window.pywebview.api.restart_app();
            setTimeout(() => { window.close(); }, 100);
        }, 1200);
    } else {
        if (loaderStatus) {
            loaderStatus.innerText = `Ошибка обновления: ${res.message}`;
            loaderStatus.style.color = "#f75a68";
        }
    }
}

function applySavedTheme() {
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'light') document.body.classList.add('light-theme');
    updateThemeIcon();
}

function toggleTheme() {
    document.body.classList.toggle('light-theme');
    localStorage.setItem('theme', document.body.classList.contains('light-theme') ? 'light' : 'dark');
    updateThemeIcon();
}

function updateThemeIcon() {
    const btn = document.querySelector('.btn--icon');
    if (btn) btn.textContent = document.body.classList.contains('light-theme') ? '☀️' : '🌙';
}

function addLoaderLog(msg) {
    const logBox = document.getElementById('loader-logs');
    if (logBox) {
        const line = document.createElement('div');
        line.className = 'log-line info';
        line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        logBox.appendChild(line);
        logBox.scrollTop = logBox.scrollHeight;
    }
}

function skipUpdate() {
    document.getElementById('version-overlay').classList.add('hidden');
    document.getElementById('loader').classList.add('hidden');
}

// ======================== КЛЮЧИ ========================

const serviceFields = {
    yandex: ['oauth_token', 'user_id', 'metric_id', 'contact_path', 'sitemap_path'],
    google: ['client_id', 'client_secret', 'access_token', 'auth_code', 'sitemap_path']
};

function setKeyValue(service, field, value) {
    document.querySelectorAll(`[data-service="${service}"][data-field="${field}"]`)
        .forEach(el => { el.value = value ?? ''; });
}

function getKeyValue(service, field) {
    const el = document.querySelector(`[data-service="${service}"][data-field="${field}"]`);
    return el ? el.value.trim() : '';
}

function syncKeys(service, source) {
    serviceFields[service].forEach(field => {
        const el = source.querySelector(`[data-service="${service}"][data-field="${field}"]`);
        const value = el ? el.value.trim() : '';
        setKeyValue(service, field, value);
    });
}

function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el && value !== undefined && value !== null) el.value = value;
}

function getInputValue(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

async function loadGlobalKeys() {
    try {
        const [yandexCfg, googleCfg] = await Promise.all([
            window.pywebview.api.get_config('yandex'),
            window.pywebview.api.get_config('google')
        ]);

        setKeyValue('yandex', 'oauth_token', yandexCfg.oauth_token);
        setKeyValue('yandex', 'user_id', yandexCfg.user_id);
        setKeyValue('yandex', 'metric_id', yandexCfg.metric_id);
        setKeyValue('yandex', 'contact_path', yandexCfg.contact_path);
        setKeyValue('yandex', 'sitemap_path', yandexCfg.sitemap_path);

        setKeyValue('google', 'client_id', googleCfg.client_id);
        setKeyValue('google', 'client_secret', googleCfg.client_secret);
        setKeyValue('google', 'access_token', googleCfg.access_token);
        setKeyValue('google', 'auth_code', googleCfg.auth_code);
        setKeyValue('google', 'sitemap_path', googleCfg.sitemap_path);
    } catch (err) {
        addLoaderLog(`⚠️ Ошибка загрузки ключей: ${err.message}`);
    }
}

async function saveKeys(service, event) {
    const context = event.target.closest('section');
    const data = {};
    serviceFields[service].forEach(field => {
        const el = context.querySelector(`[data-service="${service}"][data-field="${field}"]`);
        if (el) data[field] = el.value.trim();
    });

    const result = await window.pywebview.api.save_config(service, data);

    if (result.success) {
        syncKeys(service, context);
        showToast(`Ключи ${service} сохранены`);
    } else {
        showToast('Ошибка сохранения', 'error');
    }
}

// ======================== НАВИГАЦИЯ ========================

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav__item').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    document.querySelector(`.nav__item[data-tab="${tabName}"]`).classList.add('active');
}

async function launchBrowser(service) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Запуск...';
    try {
        const res = await window.pywebview.api.launch_browser(service);
        showToast(res.message, res.success ? 'success' : 'error');
    } catch (err) {
        showToast(`Ошибка: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = `🌐 Браузер (порт ${service === 'yandex' ? 9229 : 9227})`;
    }
}

// ======================== ACCORDION ========================

function toggleAccordion(id) {
    const header = document.querySelector(`#${id}-accordion .accordion__header`);
    const body = document.getElementById(`${id}-body`);
    if (!body) return;
    body.classList.toggle('hidden');
    header.classList.toggle('open');
}

// ======================== РЕЕСТР И СКРИПТЫ ========================

window._registries = { yandex: null, google: null };
window._scriptsLists = { yandex: [], google: [] };

async function loadScriptsLists() {
    try {
        const [yReg, gReg, yRes, gRes] = await Promise.all([
            window.pywebview.api.get_registry('yandex'),
            window.pywebview.api.get_registry('google'),
            window.pywebview.api.get_scripts_list('yandex'),
            window.pywebview.api.get_scripts_list('google')
        ]);

        window._registries.yandex = yReg;
        window._registries.google = gReg;
        window._scriptsLists.yandex = yRes.scripts || [];
        window._scriptsLists.google = gRes.scripts || [];

        renderServicePage('yandex');
        renderServicePage('google');
    } catch (err) {
        addLoaderLog(`⚠️ Ошибка загрузки скриптов: ${err.message}`);
    }
}

function isScriptInRegistry(service, scriptName) {
    const registry = window._registries[service];
    if (!registry) return false;
    for (const cat of registry.categories) {
        for (const sub of (cat.subcategories || [])) {
            if (sub.script === scriptName) return true;
        }
    }
    return false;
}

function findSubcategoryForScript(service, scriptName) {
    const registry = window._registries[service];
    if (!registry) return null;
    for (const cat of registry.categories) {
        for (const sub of (cat.subcategories || [])) {
            if (sub.script === scriptName) return { category: cat, subcategory: sub };
        }
    }
    return null;
}

// ======================== РЕНДЕР СТРАНИЦЫ СЕРВИСА ========================

function renderServicePage(service) {
    const registry = window._registries[service];
    const scripts = window._scriptsLists[service];
    if (!registry) return;

    renderCategoryNav(service, registry);

    const testScripts = scripts.filter(s => !isScriptInRegistry(service, s.name));
    renderTestsSection(service, testScripts);
}

// ======================== НАВИГАЦИЯ ПО КАТЕГОРИЯМ ========================

let activeCategory = { yandex: null, google: null };

function renderCategoryNav(service, registry) {
    const container = document.getElementById(`${service}-category-nav`);
    if (!container) return;
    container.innerHTML = '';

    registry.categories.forEach(cat => {
        const btn = document.createElement('div');
        btn.className = 'category-btn';
        btn.setAttribute('data-tooltip', cat.description);

        const hasSubs = cat.subcategories && cat.subcategories.length > 0;
        btn.innerHTML = `${cat.name} ${hasSubs ? '<span class="category-btn__arrow">&#9660;</span>' : ''}`;

        if (hasSubs) {
            const dropdown = document.createElement('div');
            dropdown.className = 'category-dropdown';

            cat.subcategories.forEach(sub => {
                const item = document.createElement('div');
                item.className = 'subcategory-item' + (sub.script ? '' : ' disabled');
                item.setAttribute('data-tooltip', sub.description);

                const scriptBadge = sub.script
                    ? `<span style="font-size:10px; padding:1px 5px; border-radius:3px; background:var(--border-color); margin-left:6px;">${sub.type === 'api' ? 'API' : 'Browser'}</span>`
                    : '<span style="font-size:10px; padding:1px 5px; border-radius:3px; background:var(--border-color); margin-left:6px; opacity:0.5;">Планируется</span>';

                item.innerHTML = `
                    <span class="subcategory-item__name">${sub.name}${scriptBadge}</span>
                    <span class="subcategory-item__desc">${sub.description}</span>
                `;

                if (sub.script) {
                    item.addEventListener('click', (e) => {
                        e.stopPropagation();
                        onSubcategorySelect(service, cat.id, sub.id);
                    });
                }

                dropdown.appendChild(item);
            });

            btn.appendChild(dropdown);
        }

        container.appendChild(btn);
    });
}

function onSubcategorySelect(service, categoryId, subcategoryId) {
    const registry = window._registries[service];
    const cat = registry.categories.find(c => c.id === categoryId);
    const sub = cat.subcategories.find(s => s.id === subcategoryId);
    if (!sub || !sub.script) return;

    activeCategory[service] = `${categoryId}-${subcategoryId}`;
    renderScriptPanel(service, sub.script, sub);

    document.querySelectorAll(`#${service}-category-nav .category-btn`).forEach(b => b.classList.remove('active'));
}

// ======================== ПАНЕЛЬ СКРИПТА ========================

function renderScriptPanel(service, scriptName, subcategory) {
    const container = document.getElementById(`${service}-script-content`);
    if (!container) return;

    const scriptId = `${service}-${scriptName}`;
    const fields = subcategory.fields || [];
    const savedData = JSON.parse(localStorage.getItem(`script_data_${scriptId}`) || '{}');
    const scriptInfo = window._scriptsLists[service].find(s => s.name === scriptName);
    const badgeType = scriptInfo ? (scriptInfo.type === 'py' ? 'Python' : 'JS') : (subcategory.type === 'api' ? 'API' : 'JS');
    const badgeClass = scriptInfo
        ? (scriptInfo.type === 'py' ? 'badge--py' : 'badge--js')
        : (subcategory.type === 'api' ? 'badge--api' : 'badge--js');

    const inputsHtml = fields.map(field => `
        <div class="form-group">
            <label class="form-label">${field} (по одному на строку или JSON)</label>
            <textarea class="form-control" id="${scriptId}-${field}" placeholder="Введите ${field}...">${savedData[field] || ''}</textarea>
        </div>
    `).join('');

    container.innerHTML = `
        <div class="card script-panel" id="${scriptId}-card">
            <div class="card__header" style="justify-content: space-between;">
                <div style="display:flex; gap:8px; align-items:center;">
                    <span>${scriptName}</span>
                    <span class="badge ${badgeClass}" style="font-size:10px; padding:2px 6px; border-radius:4px; background:var(--border-color);">${badgeType}</span>
                </div>
                <button class="btn btn--secondary btn--small" onclick="toggleScriptBody('${scriptId}')">&#9660;</button>
            </div>
            <div class="script-body hidden" id="${scriptId}-body">
                ${inputsHtml}
                <div class="align-right" style="justify-content: flex-start; align-items: center;">
                    <button class="btn btn--primary" onclick="runScript('${service}', '${scriptName}')">&#9654; Запустить</button>
                    <button class="btn btn--secondary" onclick="saveScriptData('${service}', '${scriptName}')">💾 Сохранить</button>
                    <span class="script-status" style="font-size: 13px; color: var(--text-muted); margin-left: auto;" id="${scriptId}-status"></span>
                </div>
                <div class="logs-container" style="margin-top: 16px;" id="${scriptId}-logs"></div>
                <div class="table-wrapper hidden" id="${scriptId}-report"></div>
            </div>
        </div>
    `;
}

function toggleScriptBody(scriptId) {
    const body = document.getElementById(`${scriptId}-body`);
    if (!body) return;
    const btn = body.parentElement.querySelector('.btn--secondary');
    if (body.classList.contains('hidden')) {
        body.classList.remove('hidden');
        if (btn) btn.innerHTML = '&#9650;';
    } else {
        body.classList.add('hidden');
        if (btn) btn.innerHTML = '&#9660;';
    }
}

// ======================== СОХРАНЕНИЕ/ЗАПУСК СКРИПТОВ ========================

function getFieldsForScript(service, scriptName) {
    const registry = window._registries[service];
    if (registry) {
        for (const cat of registry.categories) {
            for (const sub of (cat.subcategories || [])) {
                if (sub.script === scriptName) return sub.fields || [];
            }
        }
    }
    return [];
}

async function saveScriptData(service, script) {
    const fields = getFieldsForScript(service, script);
    const scriptId = `${service}-${script}`;
    const data = {};

    fields.forEach(field => {
        const val = getInputValue(`${scriptId}-${field}`);
        if (val) {
            try { data[field] = JSON.parse(val); }
            catch { data[field] = val.split('\n').map(s => s.trim()).filter(Boolean); }
        }
    });

    const res = await window.pywebview.api.save_script_data(service, script, data);
    if (res.success) {
        localStorage.setItem(`script_data_${scriptId}`, JSON.stringify(data));
        showToast('Данные скрипта сохранены');
    } else {
        showToast('Ошибка сохранения', 'error');
    }
}

function getScriptInputs(scriptId) {
    const parts = scriptId.split('-');
    const service = parts[0];
    const script = parts.slice(1).join('-');
    const fields = getFieldsForScript(service, script);
    const data = {};

    fields.forEach(field => {
        const val = getInputValue(`${scriptId}-${field}`);
        if (val) {
            try { data[field] = JSON.parse(val); }
            catch { data[field] = val.split('\n').map(s => s.trim()).filter(Boolean); }
        }
    });
    return data;
}

async function runScript(service, script) {
    const scriptId = `${service}-${script}`;
    const statusEl = document.getElementById(`${scriptId}-status`);
    const logsEl = document.getElementById(`${scriptId}-logs`);
    const reportEl = document.getElementById(`${scriptId}-report`);
    const btn = event.target;

    runningScripts[scriptId] = true;
    btn.disabled = true;
    btn.textContent = '⏳ Запуск...';
    statusEl.textContent = 'Запуск...';
    statusEl.style.color = 'var(--accent)';
    logsEl.innerHTML = '';
    reportEl.classList.add('hidden');

    try {
        await window.pywebview.api.save_script_data(service, script, getScriptInputs(scriptId));
        const res = await window.pywebview.api.run_script(service, script);
        if (!res.success) throw new Error(res.message);
        statusEl.textContent = 'Выполняется...';
    } catch (err) {
        statusEl.textContent = `Ошибка: ${err.message}`;
        statusEl.style.color = 'var(--status-error-text)';
        btn.disabled = false;
        btn.textContent = '▶ Запустить';
        runningScripts[scriptId] = false;
    }
}

// ======================== ТЕСТЫ ========================

function renderTestsSection(service, testScripts) {
    const container = document.getElementById(`${service}-tests-grid`);
    const section = document.getElementById(`${service}-tests-section`);
    if (!container || !section) return;

    if (testScripts.length === 0) {
        section.classList.add('hidden');
        return;
    }
    section.classList.remove('hidden');

    container.innerHTML = testScripts.map(script => {
        const scriptId = `${service}-${script.name}`;
        const savedData = JSON.parse(localStorage.getItem(`script_data_${scriptId}`) || '{}');
        const badgeType = script.type === 'py' ? 'Python' : 'JS';

        return `
            <div class="card" id="${scriptId}-card">
                <div class="card__header" style="justify-content: space-between;">
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span>${script.name}</span>
                        <span class="badge" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: var(--border-color);">${badgeType}</span>
                    </div>
                    <button class="btn btn--secondary btn--small" onclick="toggleScriptBody('${scriptId}')">&#9660;</button>
                </div>
                <div class="script-body hidden" id="${scriptId}-body">
                    <div class="form-group">
                        <label class="form-label">Данные (по одному на строку или JSON)</label>
                        <textarea class="form-control" id="${scriptId}-data" placeholder="Введите данные...">${savedData.data || ''}</textarea>
                    </div>
                    <div class="align-right" style="justify-content: flex-start; align-items: center;">
                        <button class="btn btn--primary" onclick="runScript('${service}', '${script.name}')">&#9654; Запустить</button>
                        <button class="btn btn--secondary" onclick="saveTestData('${service}', '${script.name}')">💾 Сохранить</button>
                        <span class="script-status" style="font-size: 13px; color: var(--text-muted); margin-left: auto;" id="${scriptId}-status"></span>
                    </div>
                    <div class="logs-container" style="margin-top: 16px;" id="${scriptId}-logs"></div>
                    <div class="table-wrapper hidden" id="${scriptId}-report"></div>
                </div>
            </div>
        `;
    }).join('');
}

async function saveTestData(service, scriptName) {
    const scriptId = `${service}-${scriptName}`;
    const val = getInputValue(`${scriptId}-data`);
    let data;
    try { data = JSON.parse(val); }
    catch { data = val.split('\n').map(s => s.trim()).filter(Boolean); }

    const res = await window.pywebview.api.save_script_data(service, scriptName, { data });
    if (res.success) {
        localStorage.setItem(`script_data_${scriptId}`, JSON.stringify({ data }));
        showToast('Данные скрипта сохранены');
    } else {
        showToast('Ошибка сохранения', 'error');
    }
}

// ======================== ЛОГИ И ОТЧЁТЫ ========================

function appendLog(key, line) {
    const scriptId = key.replace(':', '-');
    const logsEl = document.getElementById(`${scriptId}-logs`);
    if (logsEl) {
        const div = document.createElement('div');
        div.className = 'log-line';
        if (line.includes('✅') || line.includes('Успех') || line.includes('success')) div.classList.add('success');
        else if (line.includes('❌') || line.includes('Ошибка') || line.includes('error')) div.classList.add('error');
        else if (line.includes('⚠️') || line.includes('Предупрежд') || line.includes('warning')) div.classList.add('warning');
        else if (line.includes('ℹ️') || line.includes('Инфо') || line.includes('info')) div.classList.add('info');
        div.textContent = `[${new Date().toLocaleTimeString()}] ${line}`;
        logsEl.appendChild(div);
        logsEl.scrollTop = logsEl.scrollHeight;
    }
}

function scriptFinished(key) {
    const scriptId = key.replace(':', '-');
    const statusEl = document.getElementById(`${scriptId}-status`);
    const btn = document.querySelector(`#${scriptId}-card .btn--primary`);

    if (statusEl) {
        statusEl.textContent = 'Завершено';
        statusEl.style.color = 'var(--status-success-text)';
    }
    if (btn) {
        btn.disabled = false;
        btn.textContent = '▶ Запустить';
    }
    runningScripts[scriptId] = false;
}

function generateReport(scriptId) {
    const reportEl = document.getElementById(`${scriptId}-report`);
    if (!reportEl || !window._reportData || window._reportData.length === 0) return;

    reportEl.innerHTML = `
        <table class="table">
            <thead>
                <tr>
                    <th>Поддомен</th>
                    <th>Статус</th>
                    <th>Детали</th>
                    <th>Ошибка</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                ${window._reportData.map(r => `
                    <tr>
                        <td>${r.subdomain}</td>
                        <td style="color: var(--status-${r.status.toLowerCase().includes('ok') || r.status.toLowerCase().includes('успех') ? 'success' : r.status.toLowerCase().includes('error') ? 'error' : 'warning'}-text)">${r.status}</td>
                        <td>${r.details}</td>
                        <td>${r.error}</td>
                        <td><button class="btn btn--secondary btn--small" onclick="copyCell(this)">Скопировать</button></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div class="align-right">
            <button class="btn btn--secondary" onclick="copyTable('${scriptId}')">📋 Копировать таблицу</button>
        </div>
    `;
    reportEl.classList.remove('hidden');
}

function copyCell(btn) {
    const row = btn.closest('tr');
    const cells = Array.from(row.querySelectorAll('td')).slice(0, -1).map(td => td.textContent).join('\t');
    navigator.clipboard.writeText(cells);
    showToast('Строка скопирована');
}

function copyTable(scriptId) {
    const table = document.querySelector(`#${scriptId}-report table`);
    if (!table) return;
    let text = '';
    for (const row of table.rows) {
        text += Array.from(row.cells).slice(0, -1).map(c => c.textContent).join('\t') + '\n';
    }
    navigator.clipboard.writeText(text);
    showToast('Таблица скопирована');
}

// ======================== TOAST ========================

function showToast(msg, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    toast.style.cssText = `
        position: fixed; bottom: 24px; right: 24px; z-index: 1000;
        padding: 12px 20px; border-radius: 8px; font-size: 14px;
        background: var(--bg-card); border: 1px solid var(--border-color);
        box-shadow: var(--shadow); animation: slideIn 0.3s ease;
    `;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.animation = 'slideOut 0.3s ease'; setTimeout(() => toast.remove(), 300); }, 3000);
}

const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn { from { opacity: 0; transform: translateX(100px); } to { opacity: 1; transform: translateX(0); } }
    @keyframes slideOut { from { opacity: 1; transform: translateX(0); } to { opacity: 0; transform: translateX(100px); } }
`;
document.head.appendChild(style);
