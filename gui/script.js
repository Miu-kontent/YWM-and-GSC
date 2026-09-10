let runningScripts = {};
window._panelCache = {};

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
        addLoaderLog(`ℹ️ Загрузка списков скриптов ...`);
        await loadScriptsData();
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

window._scriptsData = { yandex: {}, google: {} };

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

async function loadScriptsData() {
    try {
        const [yData, gData] = await Promise.all([
            window.pywebview.api.get_scripts_data('yandex'),
            window.pywebview.api.get_scripts_data('google')
        ]);
        window._scriptsData.yandex = yData || {};
        window._scriptsData.google = gData || {};
    } catch (err) {
        addLoaderLog(`⚠️ Ошибка загрузки списков скриптов: ${err.message}`);
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


async function getYandexToken() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Получение';
    try {
        const browser = await window.pywebview.api.check_browser('yandex');
        if (!browser.running) {
            showToast('Откройте браузер кнопкой "🌐 Браузер (порт 9229)"', 'error');
            return;
        }
        showToast('Откройте страницу авторизации в браузере...', 'info');
        const result = await window.pywebview.api.start_yandex_get_token();
        if (result.log) result.log.forEach(line => console.log(`[yandex-auth] ${line}`));
        if (result.success) {
            setKeyValue('yandex', 'oauth_token', result.oauth_token);
            syncKeys('yandex', document.getElementById('tab-dashboard'));
            showToast('OAuth Token получен!', 'success');
        } else {
            showToast(result.message || 'Токен не получен', 'error');
        }
    } catch (err) {
        showToast(`Ошибка: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔑 Получить';
    }
}

async function getYandexUserId() {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Получение';
    try {
        const browser = await window.pywebview.api.check_browser('yandex');
        if (!browser.running) {
            showToast('Откройте браузер кнопкой "🌐 Браузер (порт 9229)"', 'error');
            return;
        }
        showToast('Получаем User ID...', 'info');
        const result = await window.pywebview.api.start_yandex_get_userid();
        if (result.log) result.log.forEach(line => console.log(`[yandex-auth] ${line}`));
        if (result.success) {
            setKeyValue('yandex', 'user_id', result.user_id);
            syncKeys('yandex', document.getElementById('tab-dashboard'));
            showToast('User ID получен!', 'success');
        } else {
            showToast(result.message || 'User ID не получен', 'error');
        }
    } catch (err) {
        showToast(`Ошибка: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔑 Получить';
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
    try {
        const res = await window.pywebview.api.launch_browser(service);
        showToast(res.message, res.success ? 'success' : 'error');
    } catch (err) {
        showToast(`Ошибка: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
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

// ======================== РЕНДЕР СТРАНИЦЫ СЕРВИСА ========================

function renderServicePage(service) {
    const registry = window._registries[service];
    const scripts = window._scriptsLists[service];
    if (!registry) return;

    const testsCat = registry.categories.find(c => c.id === 'tests');
    if (testsCat) {
        const existingScripts = new Set(
            (testsCat.subcategories || []).map(s => s.script).filter(Boolean)
        );
        const newSubs = scripts
            .filter(s => !existingScripts.has(s.name))
            .filter(s => !registry.categories.some(cat =>
                cat.id !== 'tests' && (cat.subcategories || []).some(sub => sub.script === s.name)
            ))
            .map(s => ({
                id: s.name,
                name: s.name,
                description: s.type === 'py' ? 'Python скрипт' : 'JS скрипт',
                script: s.name,
                type: s.type === 'py' ? 'api' : 'browser',
                fields: ['data']
            }));
        testsCat.subcategories = [...(testsCat.subcategories || []), ...newSubs];
    }

    renderCategoryNav(service, registry);
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

            let hideTimeout;
            btn.addEventListener('mouseenter', () => {
                clearTimeout(hideTimeout);
                dropdown.classList.add('visible');
            });
            btn.addEventListener('mouseleave', () => {
                hideTimeout = setTimeout(() => dropdown.classList.remove('visible'), 150);
            });
            dropdown.addEventListener('mouseenter', () => clearTimeout(hideTimeout));
            dropdown.addEventListener('mouseleave', () => {
                hideTimeout = setTimeout(() => dropdown.classList.remove('visible'), 150);
            });
        }

        container.appendChild(btn);
    });

    positionTooltips(container);
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

function positionTooltips(container) {
    const rect = container.getBoundingClientRect();
    container.querySelectorAll('[data-tooltip]').forEach(el => {
        el.classList.remove('tooltip-left', 'tooltip-right');
        const r = el.getBoundingClientRect();
        if (r.left - rect.left < 50) el.classList.add('tooltip-left');
        else if (rect.right - r.right < 50) el.classList.add('tooltip-right');
    });
}

// ======================== ПАНЕЛЬ СКРИПТА ========================

function resolveField(field) {
    if (typeof field === 'string') {
        return { name: field, type: 'textarea', label: `${field} (по одному на строку, с или без протокола)` };
    }
    return {
        name: field.name,
        type: field.type || 'textarea',
        label: field.label || field.name,
        options: field.options || []
    };
}

function renderFieldInput(field, scriptId, savedData) {
    const f = resolveField(field);
    const val = savedData[f.name] || '';
    const id = `${scriptId}-${f.name}`;

    switch (f.type) {
        case 'date':
            return `<div class="form-group">
                <label class="form-label">${f.label}</label>
                <input type="date" class="form-control" id="${id}" value="${val}">
            </div>`;
        case 'number':
            return `<div class="form-group">
                <label class="form-label">${f.label}</label>
                <input type="number" class="form-control" id="${id}" value="${val}" placeholder="${f.label}">
            </div>`;
        case 'text':
            return `<div class="form-group">
                <label class="form-label">${f.label}</label>
                <input type="text" class="form-control" id="${id}" value="${val}" placeholder="${f.label}">
            </div>`;
        case 'select':
            const options = f.options.map(o =>
                `<option value="${o.value}" ${val === o.value ? 'selected' : ''}>${o.label}</option>`
            ).join('');
            return `<div class="form-group">
                <label class="form-label">${f.label}</label>
                <select class="form-control" id="${id}">${options}</select>
            </div>`;
        default:
            let textVal = '';
            if (Array.isArray(val)) textVal = val.join('\n');
            else if (val && typeof val === 'object') textVal = JSON.stringify(val, null, 2);
            else textVal = val;
            return `<div class="form-group">
                <label class="form-label">${f.label} (по одному на строку, с или без протокола)</label>
                <textarea class="form-control" id="${id}" placeholder="Введите ${f.name}...">${escHtml(textVal)}</textarea>
            </div>`;
    }
}

function getScriptLayout(service, scriptName) {
    const registry = window._registries[service];
    if (!registry) return {};
    for (const cat of registry.categories) {
        for (const sub of (cat.subcategories || [])) {
            if (sub.script === scriptName) return sub.layout || {};
        }
    }
    return {};
}

const DEFAULT_TABLE_HEADERS = ['Сайт', 'Подтверждение', 'Статус', 'Сайтмапы', 'Статус сайтмапа', 'Рекомендации', 'Ошибки'];

function getSavedSelection(service, scriptName, layout) {
    const saved = window._scriptsData[service] && window._scriptsData[service][scriptName];
    if (saved && Array.isArray(saved.export_groups)) return saved.export_groups;
    return [];
}

function getVisibleColumns(layout, selection) {
    if (layout.columns) {
        return layout.columns.filter(c => c.depends === 'always' || selection.includes(c.depends));
    }
    const headers = layout.tableHeaders || DEFAULT_TABLE_HEADERS;
    const centers = layout.centerColumns || [];
    const widths = layout.columnWidths || {};
    return headers.map((label, i) => ({ label, center: centers.includes(i), width: widths[i] || null }));
}

function buildTheadHtml(layout, selection) {
    return getVisibleColumns(layout, selection).map(c => {
        const style = c.width ? ` style="width:${c.width}"` : '';
        const cls = c.center ? ' class="center"' : '';
        return `<th${cls}${style}>${escHtml(c.label)}</th>`;
    }).join('');
}

function collectExportGroups(scriptId) {
    const body = document.getElementById(`${scriptId}-body`);
    const keys = [];
    if (body) body.querySelectorAll('[data-export-group]:checked').forEach(cb => keys.push(cb.value));
    return keys;
}

async function onExportGroupChange(service, script) {
    const scriptId = `${service}-${script}`;
    const layout = getScriptLayout(service, script) || {};
    if (!layout.exportGroups) return;

    const data = getScriptInputs(scriptId);
    await window.pywebview.api.save_script_data(service, script, data);
    window._scriptsData[service][script] = data;

    const selection = collectExportGroups(scriptId);
    const thead = document.querySelector(`#${scriptId}-report thead`);
    if (thead) thead.innerHTML = `<tr>${buildTheadHtml(layout, selection)}</tr>`;
    if (layout.splitSummary) renderSummary(scriptId, null, selection);
}

function renderScriptPanel(service, scriptName, subcategory) {
    const container = document.getElementById(`${service}-script-content`);
    if (!container) return;

    const scriptId = `${service}-${scriptName}`;

    const prevTbody = document.querySelector(`#${scriptId}-report tbody`);
    const prevSummary = document.getElementById(`${scriptId}-summary`);
    const prevStatus = document.getElementById(`${scriptId}-status`);
    const prevActions = document.querySelector(`#${scriptId}-report .table-actions`);
    const prevLogs = document.getElementById(`${scriptId}-logs`);
    if (prevTbody || prevSummary || prevStatus) {
        window._panelCache[scriptId] = {
            tbody: prevTbody ? prevTbody.innerHTML : '',
            summary: prevSummary ? prevSummary.innerHTML : '',
            statusText: prevStatus ? prevStatus.textContent : '',
            statusColor: prevStatus ? prevStatus.style.color : '',
            actions: prevActions ? prevActions.outerHTML : '',
            logs: prevLogs ? prevLogs.innerHTML : ''
        };
    }

    const fields = subcategory.fields || [];
    const savedData = window._scriptsData[service][scriptName] || {};
    const scriptInfo = window._scriptsLists[service].find(s => s.name === scriptName);
    const badgeType = scriptInfo ? (scriptInfo.type === 'py' ? 'Python' : 'JS') : (subcategory.type === 'api' ? 'API' : 'JS');
    const badgeClass = scriptInfo
        ? (scriptInfo.type === 'py' ? 'badge--py' : 'badge--js')
        : (subcategory.type === 'api' ? 'badge--api' : 'badge--js');
    const layout = getScriptLayout(service, scriptName) || {};
    const selection = getSavedSelection(service, scriptName, layout);

    const inputsHtml = (fields || []).map(field => renderFieldInput(field, scriptId, savedData)).join('');

    const statusStyle = layout.statusRolling
        ? 'font-size: 13px; color: var(--text-muted); flex: 1; margin-left: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'
        : 'font-size: 13px; color: var(--text-muted); margin-left: auto;';

    const saveBtn = layout.hideSave
        ? ''
        : `<button class="btn btn--secondary" onclick="saveScriptData('${service}', '${scriptName}')">💾 Сохранить</button>`;

    const groupsHtml = (layout.exportGroups && layout.exportGroups.length)
        ? `<div class="export-groups" id="${scriptId}-groups">` + layout.exportGroups.map(g => {
            const checked = selection.includes(g.key) ? ' checked' : '';
            return `<label class="export-group" title="${escHtml(g.tooltip || '')}">
                <input type="checkbox" value="${g.key}" data-export-group="${g.key}" onchange="onExportGroupChange('${service}', '${scriptName}')"${checked}> ${escHtml(g.label)}
            </label>`;
        }).join('') + `</div>`
        : '';

    const logsHtml = layout.hideLogs
        ? ''
        : `<div class="logs-container" style="margin-top: 16px;" id="${scriptId}-logs"></div>`;

    const summaryBlock = layout.splitSummary
        ? `<div class="split-summary">
            <label class="form-label">${layout.summaryLabel || 'Сводка'}</label>
            <div class="summary-block" id="${scriptId}-summary"></div>
           </div>`
        : `<div class="summary-block hidden" id="${scriptId}-summary"></div>`;

    const topHtml = layout.splitSummary
        ? `<div class="split-row">
            <div class="split-inputs">${inputsHtml}</div>
            ${summaryBlock}
           </div>`
        : inputsHtml;

    const theadHtml = buildTheadHtml(layout, selection);

    container.innerHTML = `
        <div class="card script-panel" id="${scriptId}-card">
            <div class="card__header" style="justify-content: space-between;">
                <div style="display:flex; gap:8px; align-items:center;">
                    <span>${scriptName}</span>
                    <span class="badge ${badgeClass}" style="font-size:10px; padding:2px 6px; border-radius:4px; background:var(--border-color);">${badgeType}</span>
                </div>
            </div>
            <div class="script-body" id="${scriptId}-body">
                ${topHtml}
                <div class="align-right" style="justify-content: flex-start; align-items: center;">
                    <button class="btn btn--primary" onclick="runScript('${service}', '${scriptName}')">&#9654; Запустить</button>
                    ${saveBtn}
                    ${groupsHtml}
                    <span class="script-status" style="${statusStyle}" id="${scriptId}-status"></span>
                </div>
                ${logsHtml}
                <div class="table-wrapper" id="${scriptId}-report">
                    <table class="table">
                        <thead>
                            <tr>${theadHtml}</tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>
    `;

    const cached = window._panelCache[scriptId];
    if (cached) {
        const newTbody = document.querySelector(`#${scriptId}-report tbody`);
        if (newTbody && cached.tbody) newTbody.innerHTML = cached.tbody;
        const newSummary = document.getElementById(`${scriptId}-summary`);
        if (newSummary && cached.summary) {
            newSummary.innerHTML = cached.summary;
            newSummary.classList.remove('hidden');
        }
        const newStatus = document.getElementById(`${scriptId}-status`);
        if (newStatus && cached.statusText) {
            newStatus.textContent = cached.statusText;
            newStatus.style.color = cached.statusColor;
        }
        if (cached.actions) {
            const report = document.getElementById(`${scriptId}-report`);
            if (report) report.insertAdjacentHTML('beforeend', cached.actions);
        }
        const newLogs = document.getElementById(`${scriptId}-logs`);
        if (newLogs && cached.logs) newLogs.innerHTML = cached.logs;
    } else if (layout.splitSummary) {
        renderSummary(scriptId, null, selection);
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
        const f = resolveField(field);
        const val = getInputValue(`${scriptId}-${f.name}`);
        if (val) {
            if (f.type === 'textarea') {
                try { data[f.name] = JSON.parse(val); }
                catch { data[f.name] = val.split('\n').map(s => s.trim()).filter(Boolean); }
            } else if (f.type === 'number') {
                data[f.name] = Number(val);
            } else {
                data[f.name] = val;
            }
        }
    });

    if (getScriptLayout(service, script).exportGroups) {
        data.export_groups = collectExportGroups(scriptId);
    }

    const res = await window.pywebview.api.save_script_data(service, script, data);
    if (res.success) {
        window._scriptsData[service][script] = data;
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
        const f = resolveField(field);
        const val = getInputValue(`${scriptId}-${f.name}`);
        if (val) {
            if (f.type === 'textarea') {
                try { data[f.name] = JSON.parse(val); }
                catch { data[f.name] = val.split('\n').map(s => s.trim()).filter(Boolean); }
            } else if (f.type === 'number') {
                data[f.name] = Number(val);
            } else {
                data[f.name] = val;
            }
        }
    });
    if (getScriptLayout(service, script).exportGroups) {
        data.export_groups = collectExportGroups(scriptId);
    }
    return data;
}

async function runScript(service, script) {
    const scriptId = `${service}-${script}`;
    delete window._panelCache[scriptId];
    const layout = getScriptLayout(service, script) || {};
    const statusEl = document.getElementById(`${scriptId}-status`);
    const logsEl = document.getElementById(`${scriptId}-logs`);
    const reportEl = document.getElementById(`${scriptId}-report`);
    const summaryEl = document.getElementById(`${scriptId}-summary`);
    const btn = event.target;

    runningScripts[scriptId] = true;
    btn.disabled = true;
    btn.textContent = '⏳ Запуск...';
    statusEl.textContent = 'Запуск...';
    statusEl.style.color = 'var(--accent)';
    if (logsEl) logsEl.innerHTML = '';
    if (reportEl) {
        const tbody = reportEl.querySelector('tbody');
        if (tbody) tbody.innerHTML = '';
    }
    if (summaryEl) {
        if (layout.splitSummary) {
            renderSummary(scriptId, null);
        } else {
            summaryEl.innerHTML = '';
            summaryEl.classList.add('hidden');
        }
    }

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

// ======================== ЛОГИ И ОТЧЁТЫ ========================

function appendLog(key, line) {
    const scriptId = key.replace(':', '-');

    if (line.startsWith('__SUMMARY__:')) {
        try {
            const data = JSON.parse(line.slice(line.indexOf(':') + 1));
            updateSummary(scriptId, data);
        } catch (e) { /* ignore bad JSON */ }
        return;
    }
    if (line.startsWith('__TABLE_ROW__:')) {
        try {
            const data = JSON.parse(line.slice(line.indexOf(':') + 1));
            appendTableRow(scriptId, data);
        } catch (e) { /* ignore bad JSON */ }
        return;
    }
    if (line.startsWith('__TABLE_DONE__:')) {
        finalizeTable(scriptId);
        return;
    }

    const dashIdx = scriptId.indexOf('-');
    const service = dashIdx === -1 ? scriptId : scriptId.slice(0, dashIdx);
    const script = dashIdx === -1 ? '' : scriptId.slice(dashIdx + 1);
    const layout = getScriptLayout(service, script) || {};

    if (layout.hideLogs && layout.statusRolling) {
        console.log(`[${scriptId}] ${line}`);
        const statusEl = document.getElementById(`${scriptId}-status`);
        if (statusEl && line.trim()) {
            statusEl.textContent = line;
            if (line.includes('❌') || line.includes('Ошибка')) statusEl.style.color = 'var(--status-error-text)';
            else if (line.includes('⚠️')) statusEl.style.color = 'var(--status-warning-text)';
            else if (line.includes('✅')) statusEl.style.color = 'var(--status-success-text)';
            else statusEl.style.color = 'var(--text-muted)';
        }
        return;
    }

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

// ======================== SUMMARY / TABLE PROTOCOL ========================

function renderSummary(scriptId, data, selection) {
    const el = document.getElementById(`${scriptId}-summary`);
    if (!el) return;
    el.classList.remove('hidden');

    const dashIdx = scriptId.indexOf('-');
    const service = dashIdx === -1 ? scriptId : scriptId.slice(0, dashIdx);
    const script = dashIdx === -1 ? '' : scriptId.slice(dashIdx + 1);
    const layout = getScriptLayout(service, script) || {};
    let keys = [];

    if (layout.summaryRows) {
        if (!selection) selection = collectExportGroups(scriptId);
        keys = layout.summaryRows.filter(r => r.depends === 'always' || selection.includes(r.depends)).map(r => r.key);
    } else {
        keys = layout.summaryKeys || [];
    }

    if (keys.length === 0) {
        keys = data ? Object.keys(data) : [];
    }

    const lines = [];
    const extraKeys = data ? Object.keys(data).filter(k => !keys.includes(k)) : [];
    const allKeys = keys.concat(extraKeys);

    for (const key of allKeys) {
        const value = (data && data[key] !== undefined) ? data[key] : '—';
        lines.push(`<div class="summary-line"><span class="summary-label">${escHtml(key)}:</span> <span class="summary-value">${escHtml(String(value))}</span></div>`);
    }
    el.innerHTML = lines.join('');
}

function updateSummary(scriptId, data) {
    renderSummary(scriptId, data);
}

function appendTableRow(scriptId, data) {
    const el = document.getElementById(`${scriptId}-report`);
    if (!el) return;
    el.classList.remove('hidden');
    const tbody = el.querySelector('tbody');
    if (!tbody) return;

    const dashIdx = scriptId.indexOf('-');
    const service = dashIdx === -1 ? scriptId : scriptId.slice(0, dashIdx);
    const script = dashIdx === -1 ? '' : scriptId.slice(dashIdx + 1);
    const layout = getScriptLayout(service, script) || {};
    const cols = layout.columns && layout.exportGroups
        ? getVisibleColumns(layout, collectExportGroups(scriptId))
        : getVisibleColumns(layout, []);
    const centerCols = [];
    cols.forEach((c, i) => { if (c.center) centerCols.push(i); });

    const cells = data.cells || [];
    const tr = document.createElement('tr');
    for (let i = 0; i < cells.length; i++) {
        const cell = cells[i];
        const td = document.createElement('td');
        if (Array.isArray(cell)) {
            td.innerHTML = cell.map(item => {
                if (typeof item === 'object' && item !== null) {
                    return `<div class="sitemap-item"><span class="sitemap-path">${escHtml(item.path || '')}</span> <span class="sitemap-status ${item.status === 'OK' ? 'status-ok' : item.status === 'ERROR' ? 'status-error' : 'status-pending'}">${escHtml(item.status || '')}</span></div>`;
                }
                return `<div class="mirror-item">${escHtml(String(item))}</div>`;
            }).join('');
        } else {
            td.textContent = String(cell);
        }
        if (centerCols.includes(i)) td.classList.add('center');
        tr.appendChild(td);
    }
    tbody.appendChild(tr);
}

function finalizeTable(scriptId) {
    const el = document.getElementById(`${scriptId}-report`);
    if (!el) return;
    const existing = el.querySelector('.table-actions');
    if (existing) return;
    const actions = document.createElement('div');
    actions.className = 'table-actions';
    actions.innerHTML = `<button class="btn btn--secondary" onclick="copyTable('${scriptId}')">📋 Копировать таблицу</button>`;
    el.appendChild(actions);
}

function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function copyTable(scriptId) {
    const table = document.querySelector(`#${scriptId}-report table`);
    if (!table) return;
    let text = '';
    for (const row of table.rows) {
        text += Array.from(row.cells).map(c => c.textContent).join('\t') + '\n';
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
