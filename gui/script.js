let currentTab = 'dashboard';
let runningScripts = {};

// Вспомогательная функция ожидания загрузки элементов страницы (DOM)
function onDOMReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}

window.addEventListener('pywebviewready', () => {
    onDOMReady(async () => {
        try {
            // 0. Сначала инициализируем настройки (тему), чтобы интерфейс не "моргал"
            await applySavedTheme();

            // 1. Показываем подготовленное окно
            const loaderStatus = document.getElementById('loader-status');
            const loader = document.getElementById('loader');
            const versionOverlay = document.getElementById('version-overlay');

            if (loaderStatus) loaderStatus.innerText = "Проверка обновлений...";

            // 2. Запрос проверки версий в Python API
            const updateCheck = await window.pywebview.api.check_updates();

            const verLabel = document.getElementById('launcher-version');
            if (verLabel) verLabel.innerText = `v${updateCheck.local_version}`;

            // 3. Проверяем наличие новой версии лаунчера
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

            // await loadGlobalKeys();
            // await loadScriptsLists();       
    })
})

async function doUpdate() {
    const versionOverlay = document.getElementById('version-overlay');
    const loaderStatus = document.getElementById('loader-status');

    if (versionOverlay) versionOverlay.classList.add('hidden');
    if (loaderStatus) loaderStatus.innerText = "Скачивание и установка обновления...";

    const res = await window.pywebview.api.update_app();

    if (res && res.success) {
        if (loaderStatus) loaderStatus.innerText = "Обновление установлено! Перезапуск...";
        
        setTimeout(() => {
            // Отправляем команду на запуск нового процесса
            window.pywebview.api.restart_app();
            
            // Сразу же закрываем текущее окно UI
            setTimeout(() => { 
                window.close(); 
            }, 100);
            
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

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav__item').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    document.querySelector(`.nav__item[data-tab="${tabName}"]`).classList.add('active');
    currentTab = tabName;
}

async function loadGlobalKeys() {
    try {
        const [yandexCfg, googleCfg] = await Promise.all([
            window.pywebview.api.get_config('yandex'),
            window.pywebview.api.get_config('google')
        ]);

        setInputValue('yandex_oauth_token', yandexCfg.oauth_token);
        setInputValue('yandex_user_id', yandexCfg.user_id);
        setInputValue('yandex_metric_id', yandexCfg.metricCounterId);
        setInputValue('yandex_contact_path', yandexCfg.contactPath || 'contacts');

        setInputValue('google_client_id', googleCfg.client_id);
        setInputValue('google_client_secret', googleCfg.client_secret);
        setInputValue('google_access_token', googleCfg.access_token);
        setInputValue('google_refresh_token', googleCfg.refresh_token);
        setInputValue('google_auth_code', googleCfg.auth_code);
        setInputValue('google_redirect_uri', googleCfg.redirect_uri || 'http://localhost:3000/');
        setInputValue('google_sitemap_path', googleCfg.sitemap_path || '/sitemap/');
        setInputValue('google_main_resource', googleCfg.main_resource || 'https://medcentr-cristall.ru/');
    } catch (err) {
        console.error('Ошибка загрузки ключей:', err);
    }
}

function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el && value) el.value = value;
}

async function saveGlobalKeys() {
    const yandexData = {
        oauth_token: getInputValue('yandex_oauth_token'),
        user_id: getInputValue('yandex_user_id'),
        metricCounterId: getInputValue('yandex_metric_id'),
        contactPath: getInputValue('yandex_contact_path') || 'contacts'
    };
    const googleData = {
        client_id: getInputValue('google_client_id'),
        client_secret: getInputValue('google_client_secret'),
        access_token: getInputValue('google_access_token'),
        refresh_token: getInputValue('google_refresh_token'),
        auth_code: getInputValue('google_auth_code'),
        redirect_uri: getInputValue('google_redirect_uri') || 'http://localhost:3000/',
        sitemap_path: getInputValue('google_sitemap_path') || '/sitemap/',
        main_resource: getInputValue('google_main_resource') || 'https://medcentr-cristall.ru/'
    };

    const [yRes, gRes] = await Promise.all([
        window.pywebview.api.save_config('yandex', yandexData),
        window.pywebview.api.save_config('google', googleData)
    ]);

    if (yRes.success && gRes.success) {
        showToast('Ключи сохранены');
        await loadKeysSummary();
    } else {
        showToast('Ошибка сохранения', 'error');
    }
}

function getInputValue(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
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

async function loadKeysSummary() {
    const [yandexCfg, googleCfg] = await Promise.all([
        window.pywebview.api.get_config('yandex'),
        window.pywebview.api.get_config('google')
    ]);

    renderKeysSummary('yandex-keys-summary', 'yandex', yandexCfg);
    renderKeysSummary('google-keys-summary', 'google', googleCfg);
}

function renderKeysSummary(containerId, service, cfg) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const fields = service === 'yandex'
        ? [{label: 'OAuth', val: cfg.oauth_token}, {label: 'User ID', val: cfg.user_id}, {label: 'Metric ID', val: cfg.metricCounterId}, {label: 'Contact', val: cfg.contactPath}]
        : [{label: 'Client ID', val: cfg.client_id}, {label: 'Secret', val: cfg.client_secret}, {label: 'Access Token', val: cfg.access_token}, {label: 'Refresh', val: cfg.refresh_token}, {label: 'Sitemap', val: cfg.sitemap_path}, {label: 'Main Res', val: cfg.main_resource}];

    container.innerHTML = fields.map(f => `
        <span><span class="key-label">${f.label}:</span> <span class="key-value">${maskValue(f.val)}</span></span>
    `).join('');
}

function maskValue(val) {
    if (!val) return 'не задан';
    if (val.length <= 8) return '***';
    return val.slice(0, 4) + '***' + val.slice(-4);
}

async function loadScriptsLists() {
    try {
        const [yRes, gRes] = await Promise.all([
            window.pywebview.api.get_scripts_list('yandex'),
            window.pywebview.api.get_scripts_list('google')
        ]);

        renderScriptsPanel('yandex', yRes.scripts || []);
        renderScriptsPanel('google', gRes.scripts || []);
    } catch (err) {
        console.error('Ошибка загрузки скриптов:', err);
    }
}

const yandexScriptFields = {
    'yandex_verify': ['links', 'yandexSettings'],
    'addRegions': ['links', 'city', 'contactPath'],
    'metrika_bind': ['metricCounterId'],
    'addMetrics': ['links', 'yandexSettings'],
    'sitemap': ['links', 'yandexSettings'],
    'reindex': ['links'],
    'recrawl': ['links', 'yandexSettings'],
    'Regi': ['links'],
    'metriks': ['links', 'metricCounterId'],
    'recomen': ['links'],
    'errors': ['links'],
    'yandex_sites_to_delete': ['yandex_sites_to_delete'],
    'userid': ['yandexSettings']
};

const googleScriptFields = {
    'gsc_add_sites': ['gsc_subdomains'],
    'gsc_verify': ['gsc_subdomains'],
    'gsc_add_sitemap': ['gsc_subdomains', 'gsc_sitemap_path'],
    'gsc_delete_sites': ['gsc_sites_to_delete'],
    'gsc_delete_unverified': ['gsc_sites_to_delete'],
    'userid': []
};

function renderScriptsPanel(service, scripts) {
    const container = document.getElementById(`${service}-scripts`);
    if (!container) return;

    const fieldsMap = service === 'yandex' ? yandexScriptFields : googleScriptFields;

    container.innerHTML = scripts.map(script => {
        const fields = fieldsMap[script] || [];
        const scriptId = `${service}-${script}`;
        const savedData = JSON.parse(localStorage.getItem(`script_data_${scriptId}`) || '{}');

        const inputsHtml = fields.map(field => `
            <div class="form-group">
                <label class="form-label">${field} (по одному на строку или JSON)</label>
                <textarea class="form-control" id="${scriptId}-${field}" placeholder="Введите ${field}...">${savedData[field] || ''}</textarea>
            </div>
        `).join('');

        return `
            <div class="card" id="${scriptId}-card">
                <div class="card__header" style="justify-content: space-between;">
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span>${script}</span> 
                        <span class="badge ${script.endsWith('.py') ? 'badge--py' : 'badge--js'}" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: var(--border-color);">${script.endsWith('.py') ? 'Python' : 'JS'}</span>
                    </div>
                    <button class="btn btn--secondary btn--small" onclick="toggleScriptBody('${scriptId}')">⌄</button>
                </div>
                <div class="script-body hidden" id="${scriptId}-body">
                    ${inputsHtml}
                    <div class="align-right" style="justify-content: flex-start; align-items: center;">
                        <button class="btn btn--primary" onclick="runScript('${service}', '${script}')">▶ Запустить</button>
                        <button class="btn btn--secondary" onclick="saveScriptData('${service}', '${script}')">💾 Сохранить</button>
                        <span class="script-status" style="font-size: 13px; color: var(--text-muted); margin-left: auto;" id="${scriptId}-status"></span>
                    </div>
                    <div class="logs-container" style="margin-top: 16px;" id="${scriptId}-logs"></div>
                    <div class="table-wrapper hidden" id="${scriptId}-report"></div>
                </div>
            </div>
        `;
    }).join('');
}

function toggleScriptBody(scriptId) {
    const body = document.getElementById(`${scriptId}-body`);
    const btn = document.querySelector(`#${scriptId}-card .script-header button`);
    if (body.classList.contains('hidden')) {
        body.classList.remove('hidden');
        btn.textContent = '⌃';
    } else {
        body.classList.add('hidden');
        btn.textContent = '⌄';
    }
}

async function saveScriptData(service, script) {
    const fieldsMap = service === 'yandex' ? yandexScriptFields : googleScriptFields;
    const fields = fieldsMap[script] || [];
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
        await loadKeysSummary();
    } else {
        showToast('Ошибка сохранения', 'error');
    }
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
    statusEl.style.color = 'var(--accent-warning)';
    logsEl.innerHTML = '';
    reportEl.classList.add('hidden');

    try {
        await window.pywebview.api.save_script_data(service, script, getScriptInputs(scriptId));
        const res = await window.pywebview.api.run_script(service, script);
        if (!res.success) throw new Error(res.message);
        statusEl.textContent = 'Выполняется...';
        statusEl.style.color = 'var(--accent-yandex)';
    } catch (err) {
        statusEl.textContent = `Ошибка: ${err.message}`;
        statusEl.style.color = 'var(--accent-error)';
        btn.disabled = false;
        btn.textContent = '▶ Запустить';
        runningScripts[scriptId] = false;
    }
}

function getScriptInputs(scriptId) {
    const fieldsMap = scriptId.startsWith('yandex-') ? yandexScriptFields : googleScriptFields;
    const script = scriptId.split('-').slice(1).join('-');
    const fields = fieldsMap[script] || [];
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
    generateReport(scriptId);
}

function generateReport(scriptId) {
    if (reportData.length === 0) return;

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
                ${reportData.map(r => `
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