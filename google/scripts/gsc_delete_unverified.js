// =============================================================================
// УДАЛЕНИЕ ПОДДОМЕНОВ ИЗ GOOGLE SEARCH CONSOLE
// =============================================================================

const { loadConfig } = require('./loadConfig');
const config = loadConfig('gsc_delete_unverified');
if (!config) process.exit(1);

const { gsc_sites_to_delete } = config;
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

// =============================================================================
// 1. ЗАГРУЗКА .env
// =============================================================================

function loadEnvFromArrays() {
    const envPath = path.join(__dirname, '..', '.env');
    if (!fs.existsSync(envPath)) {
        console.log('❌ Файл .env не найден!');
        return false;
    }

    console.log(`✅ Найден файл .env: ${envPath}`);
    const envContent = fs.readFileSync(envPath, 'utf8');
    const envLines = envContent.split('\n');

    for (const line of envLines) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
            const [key, value] = trimmed.split('=');
            if (key && value) process.env[key] = value;
        }
    }
    return true;
}

// =============================================================================
// 3. НОРМАЛИЗАЦИЯ URL
// =============================================================================

function normalizeUrl(url) {
    let normalized = url.trim();
    if (normalized.endsWith('/')) {
        normalized = normalized.slice(0, -1);
    }
    normalized = normalized.replace('https://www.', 'https://');
    return normalized;
}

// =============================================================================
// 4. ФУНКЦИЯ ОТКРЫТИЯ СПИСКА
// =============================================================================

async function openResourceList(page) {
    try {
        await page.evaluate(() => {
            const inputs = document.querySelectorAll('#resource-selector-container input');
            const input = inputs[inputs.length - 1];
            if (input) {
                input.click();
                const parent = input.closest('.rFrNMe');
                if (parent) parent.click();
            }
        });
        
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        const hasList = await page.evaluate(() => {
            const options = document.querySelectorAll('[role="option"]');
            return options.length > 0;
        });
        
        if (!hasList) {
            const inputHandle = await page.$('#resource-selector-container input');
            if (inputHandle) {
                const box = await inputHandle.boundingBox();
                if (box) {
                    await page.mouse.click(box.x + box.width/2, box.y + box.height/2);
                    await new Promise(resolve => setTimeout(resolve, 1500));
                }
            }
        }
        
        return true;
    } catch (err) {
        return false;
    }
}

// =============================================================================
// 5. ФУНКЦИЯ ПОИСКА И КЛИКА ПО КНОПКЕ ПО ТЕКСТУ
// =============================================================================

async function clickButtonByText(page, text) {
    try {
        const result = await page.evaluate((searchText) => {
            const elements = document.querySelectorAll('*');
            for (const el of elements) {
                if (el.textContent && el.textContent.trim() === searchText) {
                    if (el.tagName === 'BUTTON' || 
                        el.getAttribute('role') === 'button' ||
                        el.closest('button') ||
                        el.closest('[role="button"]')) {
                        let clickable = el;
                        if (el.closest('button')) clickable = el.closest('button');
                        if (el.closest('[role="button"]')) clickable = el.closest('[role="button"]');
                        clickable.click();
                        return true;
                    }
                    el.click();
                    return true;
                }
            }
            return false;
        }, text);
        
        return result;
    } catch (err) {
        return false;
    }
}

// =============================================================================
// 6. ФУНКЦИЯ ВЫБОРА ДОМЕНА ИЗ СПИСКА
// =============================================================================

async function selectDomain(page, domainUrl) {
    try {
        const targetClean = domainUrl.replace(/\/$/, '');
        const found = await page.evaluate((target) => {
            const items = document.querySelectorAll('[role="option"]');
            for (const item of items) {
                const label = item.getAttribute('aria-label') || 
                             item.querySelector('.utePyc')?.textContent ||
                             item.getAttribute('data-resourceid');
                if (label && label.includes(target)) {
                    item.click();
                    return true;
                }
            }
            return false;
        }, targetClean);
        
        return found;
    } catch (err) {
        return false;
    }
}

// =============================================================================
// 7. ОСНОВНАЯ ФУНКЦИЯ
// =============================================================================

async function main() {
    console.log('='.repeat(70));
    console.log('🗑️  УДАЛЕНИЕ ПОДДОМЕНОВ ИЗ GOOGLE SEARCH CONSOLE');
    console.log('='.repeat(70) + '\n');

    if (!loadEnvFromArrays()) {
        console.log('❌ Не удалось загрузить .env');
        return;
    }

    const sitesToDelete = gsc_sites_to_delete || [];
    if (sitesToDelete.length === 0) {
        console.log('❌ Нет сайтов для удаления!');
        return;
    }

    const mainResource = process.env.GSC_MAIN_RESOURCE || 'https://medcentr-cristall.ru/';
    console.log(`📍 Основной ресурс: ${mainResource}\n`);

    const browserURL = 'http://localhost:9227';
    console.log(`🔌 Подключаюсь к браузеру на порту 9227...`);

    let browser;
    try {
        browser = await puppeteer.connect({
            browserURL: browserURL,
            defaultViewport: null
        });
        console.log('✅ Подключение к браузеру установлено\n');
    } catch (error) {
        console.log(`❌ Ошибка подключения: ${error.message}`);
        console.log('   🔧 Решение: Нажмите кнопку "Google (порт 9227)" в лаунчере');
        return;
    }

    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();
    page.setDefaultTimeout(30000);
    page.setDefaultNavigationTimeout(60000);

    try {
        const gscUrl = `https://search.google.com/search-console?hl=ru&resource_id=${encodeURIComponent(mainResource)}`;
        console.log(`🔗 Открываю: ${gscUrl}`);
        
        await page.goto(gscUrl, { waitUntil: 'networkidle2' });
        console.log('✅ Страница загружена');

        // ===== ЖДЕМ КОНТЕЙНЕР =====
        console.log('🔍 Жду загрузки интерфейса...');
        await page.waitForSelector('#resource-selector-container', { timeout: 60000 });
        console.log('✅ Контейнер загружен');

        // ===== ОТКРЫВАЕМ СПИСОК =====
        console.log('🖱️ Открываю список ресурсов...');
        await openResourceList(page);
        console.log('✅ Список открыт');
        await new Promise(resolve => setTimeout(resolve, 1000));

        // ===== ЖДЕМ ЗАГРУЗКИ СПИСКА =====
        await page.waitForFunction(() => {
            const options = document.querySelectorAll('[role="option"]');
            return options.length > 1;
        }, { timeout: 30000 });
        
        console.log('✅ Список загружен');

        // ===== ПОЛУЧАЕМ ВСЕ ДОМЕНЫ =====
        console.log('📋 Получаю список поддоменов...');
        
        const gscDomains = await page.evaluate(() => {
            const items = document.querySelectorAll('[role="option"]');
            const result = [];
            for (const item of items) {
                const label = item.getAttribute('aria-label') || 
                             item.querySelector('.utePyc')?.textContent ||
                             item.getAttribute('data-resourceid');
                if (label && label.startsWith('https://')) {
                    result.push(label);
                }
            }
            return result;
        });

        console.log(`📊 Найдено поддоменов: ${gscDomains.length}`);

        // Находим пересечение
        const gscDomainsNormalized = gscDomains.map(normalizeUrl);
        const sitesToDeleteNormalized = sitesToDelete.map(s => normalizeUrl(s));
        const toDelete = sitesToDeleteNormalized.filter(s => gscDomainsNormalized.includes(s));
        const notFound = sitesToDeleteNormalized.filter(s => !gscDomainsNormalized.includes(s));

        console.log(`\n🗑️  Найдено для удаления: ${toDelete.length} из ${sitesToDelete.length}`);

        if (notFound.length > 0) {
            console.log('\n⚠️ НЕ найдены в GSC:');
            notFound.slice(0, 10).forEach(s => console.log(`   ${s}`));
            if (notFound.length > 10) console.log(`   ... и еще ${notFound.length - 10}`);
        }

        if (toDelete.length === 0) {
            console.log('✅ Нет сайтов для удаления');
            await new Promise(resolve => setTimeout(resolve, 3000));
            await browser.disconnect();
            return;
        }

        console.log('\n📋 БУДУТ УДАЛЕНЫ:');
        toDelete.forEach((url, idx) => console.log(`   ${idx + 1}. ${url}`));

        let successCount = 0;
        let errorCount = 0;
        const errorList = [];

        for (let i = 0; i < toDelete.length; i++) {
            const siteUrl = toDelete[i];
            console.log(`\n${i + 1}/${toDelete.length}: Удаляю ${siteUrl}`);

            try {
                // ===== ЗАКРЫВАЕМ СПИСОК =====
                await page.keyboard.press('Escape');
                await new Promise(resolve => setTimeout(resolve, 1000));

                // ===== ОТКРЫВАЕМ СПИСОК =====
                console.log('   🔄 Открываю список...');
                const opened = await openResourceList(page);
                if (!opened) {
                    console.log('   ❌ Не удалось открыть список');
                    errorCount++;
                    errorList.push(siteUrl);
                    continue;
                }
                
                await new Promise(resolve => setTimeout(resolve, 1500));

                // ===== ВЫБИРАЕМ ДОМЕН =====
                console.log('   🔍 Ищу домен в списке...');
                const found = await selectDomain(page, siteUrl);

                if (!found) {
                    console.log(`   ⚠️ Не найден в списке`);
                    errorCount++;
                    errorList.push(siteUrl);
                    await page.keyboard.press('Escape');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }

                console.log('   ✅ Домен выбран');
                await new Promise(resolve => setTimeout(resolve, 2000));

                // ===== НАЖИМАЕМ "УДАЛИТЬ РЕСУРС" =====
                console.log('   🔍 Ищу кнопку "Удалить ресурс"...');
                
                let deleteClicked = await clickButtonByText(page, 'Удалить ресурс');
                
                if (!deleteClicked) {
                    const result = await page.evaluate(() => {
                        const allElements = document.querySelectorAll('span, div, button');
                        for (const el of allElements) {
                            if (el.textContent && el.textContent.includes('Удалить ресурс')) {
                                let parent = el;
                                for (let i = 0; i < 5 && parent; i++) {
                                    if (parent.tagName === 'BUTTON' || 
                                        parent.getAttribute('role') === 'button' ||
                                        parent.closest('[role="button"]') ||
                                        parent.closest('button')) {
                                        const clickable = parent.closest('[role="button"]') || parent.closest('button') || parent;
                                        clickable.click();
                                        return true;
                                    }
                                    parent = parent.parentElement;
                                }
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    });
                    deleteClicked = result;
                }

                if (!deleteClicked) {
                    const xpath = "//*[contains(text(), 'Удалить ресурс')]";
                    const [element] = await page.$x(xpath);
                    if (element) {
                        await element.click();
                        deleteClicked = true;
                    }
                }

                if (!deleteClicked) {
                    console.log('   ❌ Кнопка "Удалить ресурс" не найдена');
                    errorCount++;
                    errorList.push(siteUrl);
                    await page.keyboard.press('Escape');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }

                console.log('   ✅ Нажата кнопка "Удалить ресурс"');
                await new Promise(resolve => setTimeout(resolve, 2000));

                // ===== ПОДТВЕРЖДАЕМ УДАЛЕНИЕ =====
                console.log('   🔍 Ищу кнопку "Удалить"...');
                let confirmClicked = await clickButtonByText(page, 'Удалить');

                if (!confirmClicked) {
                    const result = await page.evaluate(() => {
                        const allElements = document.querySelectorAll('span, div, button');
                        for (const el of allElements) {
                            if (el.textContent && el.textContent.trim() === 'Удалить') {
                                let parent = el;
                                for (let i = 0; i < 5 && parent; i++) {
                                    if (parent.tagName === 'BUTTON' || 
                                        parent.getAttribute('role') === 'button' ||
                                        parent.closest('[role="button"]') ||
                                        parent.closest('button')) {
                                        const clickable = parent.closest('[role="button"]') || parent.closest('button') || parent;
                                        clickable.click();
                                        return true;
                                    }
                                    parent = parent.parentElement;
                                }
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    });
                    confirmClicked = result;
                }

                if (!confirmClicked) {
                    const xpath = "//*[contains(text(), 'Удалить')]";
                    const [element] = await page.$x(xpath);
                    if (element) {
                        await element.click();
                        confirmClicked = true;
                    }
                }

                if (!confirmClicked) {
                    console.log('   ❌ Кнопка "Удалить" не найдена');
                    errorCount++;
                    errorList.push(siteUrl);
                    await page.keyboard.press('Escape');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    continue;
                }

                console.log(`   ✅ Удален`);
                successCount++;
                
                await new Promise(resolve => setTimeout(resolve, 3000));

            } catch (err) {
                console.log(`   ❌ Ошибка: ${err.message}`);
                errorCount++;
                errorList.push(siteUrl);
                try {
                    await page.keyboard.press('Escape');
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } catch (e) {}
            }
        }

        console.log('\n' + '='.repeat(70));
        console.log('📊 ИТОГИ:');
        console.log(`✅ Успешно удалено: ${successCount}`);
        console.log(`❌ Ошибок: ${errorCount}`);
        console.log(`📋 Всего: ${toDelete.length}`);
        
        if (errorList.length > 0) {
            console.log('\n🔴 ОШИБКИ:');
            errorList.forEach(url => console.log(`   ${url}`));
        }
        console.log('='.repeat(70));

        await new Promise(resolve => setTimeout(resolve, 3000));

    } catch (err) {
        console.error('❌ ОШИБКА:', err.message);
    } finally {
        await browser.disconnect();
        console.log('🔄 Отключено от браузера');
    }
}

// =============================================================================
// 8. ЗАПУСК
// =============================================================================

main().catch(err => {
    console.error('❌ ОШИБКА:', err.message);
});