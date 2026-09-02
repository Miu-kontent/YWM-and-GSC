let currentTab = 'dashboard';
let runningScripts = {};

document.addEventListener('DOMContentLoaded', async () => {
    applySavedTheme();
    await initApp();
});

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
    const btn = document.querySelector('.theme-toggle');
    if (btn) btn.textContent = document.body.classList.contains('light-theme') ? '☀️' : '🌙';
}

async function initApp() {
    const loaderStatus = document.getElementById('loader-status');
    const loaderLogs = document.getElementById('loader-logs');
    const loader = document.getElementById('loader');
    const updateModal = document.getElementById('update-modal');

    try {
        addLoaderLog('Проверка обновлений...');
        const result = await eel.check_updates()();

        if (result.success && result.update_available) {
            document.getElementById('local-ver').textContent = result.local_version;
            document.getElementById('remote-ver').textContent = result.remote_version;
            updateModal.classList.remove('hidden');
            addLoaderLog(`⚠️ Доступна версия ${result.remote_version}`);
        } else {
            addLoaderLog(`✅ Версия актуальна (${result.local_version})`);
        }
    } catch (err) {
        addLoaderLog(`⚠️ Не удалось проверить обновления: ${err.message}`);
    }

    await loadGlobalKeys();
    await loadScriptsLists();

    setTimeout(() => {
        loader.classList.add('hidden');
    }, 500);
}

function addLoaderLog(msg) {
    const el = document.getElementById('loader-logs');
    if (el) {
        const line = document.createElement('div');
        line.className = 'log-line info';
        line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        el.appendChild(line);
        el.scrollTop = el.scrollHeight;
    }
}

function skipUpdate() {
    document.getElementById('update-modal').classList.add('hidden');
    document.getElementById('loader').classList.add('hidden');
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    document.querySelector(`.nav-tab[data-tab="${tabName}"]`).classList.add('active');
    currentTab = tabName;
}

async function loadGlobalKeys() {
    try {
        const [yandexCfg, googleCfg] = await Promise.all([
            eel.get_config('yandex')(),
            eel.get_config('google')()
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
        auth_code: getInputValue('google_auth_code')
    };

    const [yRes, gRes] = await Promise.all([
        eel.save_config('yandex', yandexData)(),
        eel.save_config('google', googleData)()
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
        const res = await eel.launch_browser(service)();
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
        eel.get_config('yandex')(),
        eel.get_config('google')()
    ]);

    renderKeysSummary('yandex-keys-summary', 'yandex', yandexCfg);
    renderKeysSummary('google-keys-summary', 'google', googleCfg);
}

function renderKeysSummary(containerId, service, cfg) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const fields = service === 'yandex'
        ? [{label: 'OAuth', val: cfg.oauth_token}, {label: 'User ID', val: cfg.user_id}, {label: 'Metric ID', val: cfg.metricCounterId}, {label: 'Contact', val: cfg.contactPath}]
        : [{label: 'Client ID', val: cfg.client_id}, {label: 'Secret', val: cfg.client_secret}, {label: 'Access Token', val: cfg.access_token}, {label: 'Refresh', val: cfg.refresh_token}];

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
            eel.get_scripts_list('yandex')(),
            eel.get_scripts_list('google')()
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
            <div class="textarea-wrapper">
                <label>${field} (по одному на строку или JSON)</label>
                <textarea id="${scriptId}-${field}" placeholder="Введите ${field}...">${savedData[field] || ''}</textarea>
            </div>
        `).join('');

        return `
            <div class="script-card ${service}" id="${scriptId}-card">
                <div class="script-header">
                    <h3>${script} <span class="script-badge ${script.endsWith('.py') ? 'py' : 'js'}">${script.endsWith('.py') ? 'Python' : 'JS'}</span></h3>
                    <button class="btn btn-small" onclick="toggleScriptBody('${scriptId}')">⌄</button>
                </div>
                <div class="script-body hidden" id="${scriptId}-body">
                    ${inputsHtml}
                    <div class="script-actions">
                        <button class="btn btn-primary" onclick="runScript('${service}', '${script}')">▶ Запустить</button>
                        <button class="btn btn-secondary" onclick="saveScriptData('${service}', '${script}')">💾 Сохранить данные</button>
                        <span class="script-status" id="${scriptId}-status"></span>
                    </div>
                    <div class="logs-container" id="${scriptId}-logs"></div>
                    <div class="report-table-wrapper hidden" id="${scriptId}-report"></div>
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

    const res = await eel.save_script_data(service, script, data)();
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
        await eel.save_script_data(service, script, getScriptInputs(scriptId))();
        const res = await eel.run_script(service, script)();
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
    const btn = document.querySelector(`#${scriptId}-card .btn-primary`);

    if (statusEl) {
        statusEl.textContent = 'Завершено';
        statusEl.style.color = 'var(--accent-success)';
    }
    if (btn) {
        btn.disabled = false;
        btn.textContent = '▶ Запустить';
    }
    runningScripts[scriptId] = false;
    generateReport(scriptId);
}

function generateReport(scriptId) {
    const logsEl = document.getElementById(`${scriptId}-logs`);
    const reportEl = document.getElementById(`${scriptId}-report`);
    if (!logsEl || !reportEl) return;

    const lines = logsEl.querySelectorAll('.log-line');
    const reportData = [];

    lines.forEach(line => {
        const text = line.textContent;
        const match = text.match(/\[.*?\]\s*(.+)/);
        if (match) {
            const msg = match[1];
            if (msg.includes('→') || msg.includes('статус') || msg.includes('Status') || msg.includes('result')) {
                const parts = msg.split(/[→:]/).map(s => s.trim());
                if (parts.length >= 2) {
                    reportData.push({
                        subdomain: parts[0],
                        status: parts[1],
                        details: parts.slice(2).join(' '),
                        error: ''
                    });
                }
            }
        }
    });

    if (reportData.length === 0) return;

    reportEl.innerHTML = `
        <table class="report-table">
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
                        <td class="status-${r.status.toLowerCase().includes('ok') || r.status.toLowerCase().includes('успех') ? 'ok' : r.status.toLowerCase().includes('error') ? 'error' : 'warning'}">${r.status}</td>
                        <td>${r.details}</td>
                        <td>${r.error}</td>
                        <td><button class="copy-btn" onclick="copyCell(this)">Копировать строку</button></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div class="button-wrapper" style="margin-top: 12px;">
            <button class="btn btn-secondary" onclick="copyTable('${scriptId}')">📋 Копировать таблицу</button>
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