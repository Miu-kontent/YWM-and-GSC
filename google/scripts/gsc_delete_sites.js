const { loadConfig } = require('./loadConfig');
const config = loadConfig('gsc_delete_sites');
if (!config) process.exit(1);

const { gsc_sites_to_delete } = config;
const puppeteer = require('puppeteer');

function getSitesToDelete() {
    return gsc_sites_to_delete || [];
}

// =============================================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// =============================================================================

// 1. Проверка на ошибку 429
async function checkForRateLimit(page) {
    try {
        const pageText = await page.evaluate(() => document.body.innerText);
        if (pageText.includes('429') || pageText.includes('слишком много запросов')) {
            return true;
        }
        return false;
    } catch (error) {
        return false;
    }
}

// 2. Проверка на страницу входа
async function checkForLoginPage(page) {
    try {
        const pageText = await page.evaluate(() => document.body.innerText);
        if (pageText.includes('Вход') && (pageText.includes('Телефон или адрес эл. почты') || pageText.includes('Электронная почта'))) {
            return true;
        }
        return false;
    } catch (error) {
        return false;
    }
}

// 3. Проверка на отсутствие прав доступа
async function checkForNoAccess(page) {
    try {
        const pageText = await page.evaluate(() => document.body.innerText);
        if (pageText.includes('нет доступа к этому ресурсу') || 
            pageText.includes('No access to this resource') ||
            pageText.includes('У вас нет доступа')) {
            return true;
        }
        return false;
    } catch (error) {
        return false;
    }
}

// 4. Проверка, что страница загружена и фрейм не detached
async function isPageValid(page) {
    try {
        await page.evaluate(() => 1);
        return true;
    } catch (error) {
        return false;
    }
}

// 5. Прокрутка страницы
async function scrollPage(page) {
    try {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await new Promise(resolve => setTimeout(resolve, 1000));
        await page.evaluate(() => window.scrollTo(0, 0));
        await new Promise(resolve => setTimeout(resolve, 500));
    } catch (error) {
        // Игнорируем ошибки скролла
    }
}

// 6. Клик по кнопке "Удалить ресурс"
async function clickDeleteButton(page) {
    try {
        await scrollPage(page);
        await new Promise(resolve => setTimeout(resolve, 1000));

        const clicked = await page.evaluate(() => {
            const elements = document.querySelectorAll('div[role="button"] span.RveJvd');
            for (let el of elements) {
                if (el.textContent.trim() === 'Удалить ресурс') {
                    const parent = el.closest('div[role="button"]');
                    if (parent) {
                        parent.click();
                        return true;
                    }
                }
            }
            return false;
        });
        if (clicked) return true;
        
        const clickedXPath = await page.evaluate(() => {
            const xpath = '//div[@role="button"]//span[text()="Удалить ресурс"]';
            const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            const span = result.singleNodeValue;
            if (span) {
                const btn = span.closest('div[role="button"]');
                if (btn) {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        if (clickedXPath) return true;
        
        const clickedPartial = await page.evaluate(() => {
            const buttons = document.querySelectorAll('div[role="button"]');
            for (let btn of buttons) {
                const text = btn.textContent || '';
                if (text.includes('Удалить ресурс') || text.includes('Удалить')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        return clickedPartial;
    } catch (error) {
        return false;
    }
}

// 7. Клик по кнопке подтверждения
async function clickConfirmButton(page) {
    try {
        await page.waitForSelector('div[role="dialog"]', { timeout: 5000 });
    } catch (e) {
        return false;
    }
    await new Promise(resolve => setTimeout(resolve, 1000));

    const clicked = await page.evaluate(() => {
        const dialog = document.querySelector('div[role="dialog"]');
        if (!dialog) return false;
        
        const buttons = dialog.querySelectorAll('div[role="button"]');
        for (let btn of buttons) {
            const text = btn.textContent || '';
            if (text.includes('Удалить ресурс') || text.includes('Удалить')) {
                btn.click();
                return true;
            }
        }
        return false;
    });
    if (clicked) return true;
    
    const clickedXPath = await page.evaluate(() => {
        const xpath = '//div[@role="dialog"]//div[@role="button"]//span[contains(text(),"Удалить")]';
        const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        const span = result.singleNodeValue;
        if (span) {
            const btn = span.closest('div[role="button"]');
            if (btn) {
                btn.click();
                return true;
            }
        }
        return false;
    });
    if (clickedXPath) return true;
    
    const clickedLast = await page.evaluate(() => {
        const dialog = document.querySelector('div[role="dialog"]');
        if (!dialog) return false;
        
        const buttons = dialog.querySelectorAll('div[role="button"]');
        if (buttons.length > 0) {
            buttons[buttons.length - 1].click();
            return true;
        }
        return false;
    });
    return clickedLast;
}

// =============================================================================
// ОСНОВНАЯ ФУНКЦИЯ
// =============================================================================

(async () => {
    console.log('='.repeat(70));
    console.log('🚀 УДАЛЕНИЕ САЙТОВ ИЗ GOOGLE SEARCH CONSOLE');
    console.log('='.repeat(70) + '\n');

    const sitesToDelete = getSitesToDelete();

    if (sitesToDelete.length === 0) {
        console.log('❌ Нет сайтов для удаления!');
        console.log('   Добавьте их в массив gsc_sites_to_delete в arr.js');
        return;
    }

    console.log('📊 Всего сайтов для удаления: ' + sitesToDelete.length + '\n');
    console.log('🔌 Подключаюсь к браузеру на порту 9227...\n');

    let browser;
    try {
        browser = await puppeteer.connect({
            browserURL: 'http://localhost:9227',
            defaultViewport: null
        });
        console.log('✅ Подключение к браузеру установлено\n');
    } catch (error) {
        console.log('❌ Ошибка подключения: ' + error.message);
        return;
    }

    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();

    let success = 0;
    let errors = 0;
    let errorSites = [];
    let noAccessSites = [];
    let rateLimited = false;
    let processedCount = 0;

    for (let i = 0; i < sitesToDelete.length; i++) {
        const site = sitesToDelete[i];
        console.log('\n' + (i + 1) + '/' + sitesToDelete.length + ': ' + site);

        try {
            // --- 1. ОПРЕДЕЛЯЕМ ПРОТОКОЛ ИЗ САЙТА ---
            let protocol = 'https%3A%2F%2F';
            let cleanSite = site.replace(/\/+$/, '');
            
            if (site.startsWith('http://')) {
                protocol = 'http%3A%2F%2F';
                cleanSite = cleanSite.replace(/^http:\/\//, '');
            } else if (site.startsWith('https://')) {
                protocol = 'https%3A%2F%2F';
                cleanSite = cleanSite.replace(/^https:\/\//, '');
            } else {
                protocol = 'https%3A%2F%2F';
            }
            
            // --- 2. ФОРМИРУЕМ URL ---
            const url = `https://search.google.com/search-console/settings?resource_id=${protocol}${encodeURIComponent(cleanSite)}%2F&hl=ru`;
            
            console.log('   🔗 Протокол: ' + (site.startsWith('http://') ? 'http' : 'https'));
            console.log('   🔗 Переход: ' + url);
            
            // --- 3. ПЕРЕХОД С ПОВТОРНЫМИ ПОПЫТКАМИ ПРИ ОШИБКЕ DETACHED FRAME ---
            let gotoSuccess = false;
            for (let attempt = 1; attempt <= 3; attempt++) {
                try {
                    if (attempt > 1) {
                        console.log('   🔄 Повторная попытка перехода ' + attempt + '...');
                        // Проверяем, валидна ли страница, если нет - создаем новую
                        if (!await isPageValid(page)) {
                            console.log('   🔄 Страница повреждена, создаем новую...');
                            const newPage = await browser.newPage();
                            await page.close();
                            page = newPage;
                        }
                        await new Promise(resolve => setTimeout(resolve, 2000));
                    }
                    
                    await page.goto(url, {
                        waitUntil: 'networkidle2',
                        timeout: 30000
                    });
                    
                    gotoSuccess = true;
                    break;
                } catch (gotoError) {
                    if (gotoError.message.includes('detached')) {
                        console.log('   ⚠️ Ошибка detached frame, повтор...');
                        continue;
                    }
                    throw gotoError;
                }
            }
            
            if (!gotoSuccess) {
                console.log('   ❌ Не удалось перейти по ссылке после 3 попыток');
                errors++;
                errorSites.push(site);
                processedCount++;
                continue;
            }

            await new Promise(resolve => setTimeout(resolve, 3000));

            // --- 4. ПРОВЕРКА НА СТРАНИЦУ ВХОДА ---
            if (await checkForLoginPage(page)) {
                console.log('   🔄 Обнаружена страница входа. Пытаемся восстановить сессию...');
                
                await page.goto('https://search.google.com/search-console', {
                    waitUntil: 'networkidle2',
                    timeout: 30000
                });
                
                await new Promise(resolve => setTimeout(resolve, 3000));
                
                if (await checkForLoginPage(page)) {
                    console.log('\n' + '='.repeat(70));
                    console.log('🔐 ТРЕБУЕТСЯ РУЧНАЯ АВТОРИЗАЦИЯ');
                    console.log('='.repeat(70));
                    rateLimited = true;
                    break;
                } else {
                    console.log('   ✅ Сессия восстановлена!');
                    await page.goto(url, {
                        waitUntil: 'networkidle2',
                        timeout: 30000
                    });
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
            }

            // --- 5. ПРОВЕРКА НА ОТСУТСТВИЕ ПРАВ ---
            if (await checkForNoAccess(page)) {
                console.log('   ⛔ Нет прав доступа к этому ресурсу');
                noAccessSites.push(site);
                errors++;
                processedCount++;
                continue;
            }

            // --- 6. ПРОВЕРКА НА 429 ---
            if (await checkForRateLimit(page)) {
                console.log('\n' + '='.repeat(70));
                console.log('🚫 ОБНАРУЖЕНА ОШИБКА 429');
                console.log('='.repeat(70));
                rateLimited = true;
                break;
            }

            // --- 7. КЛИК НА "УДАЛИТЬ РЕСУРС" ---
            console.log('   🔄 Поиск кнопки "Удалить ресурс"...');
            
            let deleteClicked = false;
            for (let attempt = 1; attempt <= 5; attempt++) {
                if (attempt > 1) {
                    console.log('   🔄 Попытка ' + attempt + '...');
                    await new Promise(resolve => setTimeout(resolve, 1500));
                }
                
                try {
                    deleteClicked = await clickDeleteButton(page);
                } catch (clickError) {
                    if (clickError.message.includes('detached')) {
                        console.log('   ⚠️ Ошибка detached frame при клике');
                        // Пробуем обновить страницу
                        await page.reload({ waitUntil: 'networkidle2' });
                        await new Promise(resolve => setTimeout(resolve, 2000));
                        continue;
                    }
                    throw clickError;
                }
                
                if (deleteClicked) {
                    console.log('   ✅ Кнопка "Удалить ресурс" нажата (попытка ' + attempt + ')');
                    break;
                }
            }

            if (!deleteClicked) {
                console.log('   ❌ Кнопка "Удалить ресурс" не найдена');
                errors++;
                errorSites.push(site);
                processedCount++;
                continue;
            }

            await new Promise(resolve => setTimeout(resolve, 2000));

            // --- 8. ПОДТВЕРЖДЕНИЕ ---
            try {
                console.log('   🔄 Ожидание диалога подтверждения...');
                let confirmClicked = false;
                
                for (let attempt = 1; attempt <= 5; attempt++) {
                    if (attempt > 1) {
                        console.log('   🔄 Попытка подтверждения ' + attempt + '...');
                    }
                    
                    try {
                        confirmClicked = await clickConfirmButton(page);
                    } catch (confirmError) {
                        if (confirmError.message.includes('detached')) {
                            console.log('   ⚠️ Ошибка detached frame при подтверждении');
                            continue;
                        }
                        throw confirmError;
                    }
                    
                    if (confirmClicked) {
                        console.log('   ✅ Подтверждение отправлено (попытка ' + attempt + ')');
                        break;
                    }
                }

                if (!confirmClicked) {
                    console.log('   ❌ Кнопка подтверждения не найдена');
                    errors++;
                    errorSites.push(site);
                    processedCount++;
                    continue;
                }

            } catch (error) {
                console.log('   ❌ Ошибка при подтверждении: ' + error.message);
                errors++;
                errorSites.push(site);
                processedCount++;
                continue;
            }

            await new Promise(resolve => setTimeout(resolve, 3000));
            console.log('   ✅ Ресурс ' + site + ' удалён!');
            success++;
            processedCount++;

        } catch (error) {
            console.log('   ❌ Ошибка: ' + error.message.split('\n')[0]);
            errors++;
            errorSites.push(site);
            processedCount++;
            continue;
        }
        
        if (i < sitesToDelete.length - 1) {
            console.log('   ⏳ Пауза 2,5 секунды...');
            await new Promise(resolve => setTimeout(resolve, 2500));
        }
    }

    await browser.disconnect();

    console.log('\n' + '='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log('✅ Успешно удалено: ' + success);
    console.log('❌ Ошибок: ' + errors);
    console.log('📋 Всего обработано: ' + processedCount + ' из ' + sitesToDelete.length);
    
    if (noAccessSites.length > 0) {
        console.log('\n⛔ САЙТЫ БЕЗ ПРАВ ДОСТУПА:');
        noAccessSites.forEach((site, index) => {
            console.log('   ' + (index + 1) + '. ' + site);
        });
    }
    
    if (errorSites.length > 0 && !rateLimited) {
        console.log('\n🔴 ССЫЛКИ С ОШИБКАМИ:');
        errorSites.forEach((site, index) => {
            console.log('   ' + (index + 1) + '. ' + site);
        });
    }
    
    console.log('='.repeat(70));
})();