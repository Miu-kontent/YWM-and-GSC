const { loadConfig } = require('./loadConfig');
const puppeteer = require('puppeteer');

function getSitesToDelete() {
    const config = loadConfig('yandex_sites_to_delete');
    if (!config) return [];
    
    return config.yandex_sites_to_delete || [];
}

// =============================================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// =============================================================================

function getDeleteMode(sitesList) {
    if (!sitesList || sitesList.length === 0) { 
        return { mode: 'none', patterns: [], exactUrls: [] }; 
    }
    
    const patterns = [];
    const exactUrls = [];
    
    for (let site of sitesList) {
        const clean = site.replace(/^https?:\/\//, '').replace(/\/+$/, '');
        const parts = clean.split('.');
        
        if (parts.length <= 2) {
            patterns.push(clean);
        } else {
            exactUrls.push(site);
        }
    }
    
    if (patterns.length > 0) {
        return { 
            mode: 'mask', 
            patterns: patterns,
            exactUrls: exactUrls 
        };
    }
    
    return { 
        mode: 'exact', 
        patterns: [],
        exactUrls: sitesList 
    };
}

function matchesPattern(domain, patterns) {
    for (let pattern of patterns) {
        if (domain.includes(pattern)) {
            return true;
        }
    }
    return false;
}

// БЫСТРЫЙ поиск строки с сайтом и клик по меню
async function findSiteRowAndClickMenu(page, siteDomain) {
    const result = await page.evaluate((domain) => {
        const rows = document.querySelectorAll('tr.StarTable-Row');
        
        for (let row of rows) {
            const link = row.querySelector('a.SiteHostName-Hostname');
            if (link && link.textContent.includes(domain)) {
                const menuButton = row.querySelector('td.StarTable-Cell_name_ACTIONS button.g-dropdown-menu__switcher-button');
                if (menuButton) {
                    menuButton.click();
                    return true;
                }
            }
        }
        return false;
    }, siteDomain);
    
    return result;
}

// БЫСТРЫЙ клик по пункту "Удалить сайт"
async function clickDeleteSiteMenuItem(page) {
    try {
        await page.waitForSelector('.g-dropdown-menu__popup-content', { timeout: 3000 });
        await new Promise(resolve => setTimeout(resolve, 500));
        
        const result = await page.evaluate(() => {
            const items = document.querySelectorAll('.g-menu__item');
            for (let item of items) {
                const text = item.textContent || '';
                if (text.includes('Удалить сайт')) {
                    item.click();
                    return true;
                }
            }
            return false;
        });
        
        return result;
    } catch (error) {
        return false;
    }
}

// БЫСТРОЕ получение всех доменов на странице
async function getDomainsOnPage(page) {
    try {
        const result = await page.evaluate(() => {
            const rows = document.querySelectorAll('tr.StarTable-Row');
            const domains = [];
            for (let row of rows) {
                const link = row.querySelector('a.SiteHostName-Hostname');
                if (link) {
                    domains.push(link.textContent.trim());
                }
            }
            return domains;
        });
        return result;
    } catch (error) {
        return [];
    }
}

// БЫСТРАЯ проверка наличия таблицы
async function hasSitesTable(page) {
    try {
        const result = await page.evaluate(() => {
            return document.querySelector('table.StarTable') !== null;
        });
        return result;
    } catch (error) {
        return false;
    }
}

// =============================================================================
// ОСНОВНАЯ ФУНКЦИЯ
// =============================================================================

(async () => {
    console.log('='.repeat(70));
    console.log('🚀 УДАЛЕНИЕ САЙТОВ ИЗ ЯНДЕКС ВЕБМАСТЕРА');
    console.log('='.repeat(70) + '\n');

    const sitesToDelete = getSitesToDelete();

    if (sitesToDelete.length === 0) {
        console.log('❌ Нет сайтов для удаления!');
        return;
    }

    const deleteConfig = getDeleteMode(sitesToDelete);
    
    console.log('📊 Всего записей: ' + sitesToDelete.length);
    console.log('📋 Режим: ' + (deleteConfig.mode === 'mask' ? '🔍 МАССОВЫЙ (по маске)' : '🎯 ТОЧЕЧНЫЙ'));
    
    if (deleteConfig.mode === 'mask') {
        console.log('   🏷️  Маски: ' + deleteConfig.patterns.join(', '));
    }
    console.log('');

    console.log('🔌 Подключаюсь к браузеру на порту 9229...\n');

    let browser;
    try {
        browser = await puppeteer.connect({
            browserURL: 'http://localhost:9229',
            defaultViewport: null
        });
        console.log('✅ Подключено\n');
    } catch (error) {
        console.log('❌ Ошибка: ' + error.message);
        return;
    }

    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();

    let totalDeleted = 0;
    let totalErrors = 0;
    let errorSites = [];
    let processedSites = new Set();
    
    const maxPages = 200;
    let currentPage = 1;
    let emptyPagesCount = 0;

    console.log('🔍 Поиск и удаление...\n');

    while (currentPage <= maxPages) {
        const url = `https://webmaster.yandex.ru/sites/?noRedirect=yes&page=${currentPage}`;
        console.log(`📄 Страница ${currentPage}`);

        try {
            // Переход на страницу
            await page.goto(url, {
                waitUntil: 'domcontentloaded', // БЫСТРЕЕ: не ждем все ресурсы
                timeout: 20000
            });

            await new Promise(resolve => setTimeout(resolve, 1500)); // Меньше задержка

            // Проверяем таблицу
            const tableExists = await hasSitesTable(page);
            
            if (!tableExists) {
                emptyPagesCount++;
                if (emptyPagesCount >= 3) {
                    console.log('   ✅ Конец списка\n');
                    break;
                }
                currentPage++;
                continue;
            } else {
                emptyPagesCount = 0;
            }

            // ===== ОСНОВНАЯ ЛОГИКА: ПЕРЕСКАНИРОВАНИЕ СТРАНИЦЫ =====
            let hasMoreOnPage = true;
            let deletedOnPage = 0;
            let errorsOnPage = 0;
            
            // Пока на странице есть сайты для удаления - сканируем её
            while (hasMoreOnPage) {
                // Получаем актуальные домены на странице
                const domainsOnPage = await getDomainsOnPage(page);
                
                if (domainsOnPage.length === 0) {
                    console.log('   ✅ Страница пуста');
                    hasMoreOnPage = false;
                    break;
                }

                // Ищем сайты для удаления на ТЕКУЩЕЙ странице
                let sitesToRemove = [];
                
                if (deleteConfig.mode === 'mask') {
                    for (let domain of domainsOnPage) {
                        const domainClean = domain.replace(/^https?:\/\//, '').replace(/\/+$/, '');
                        if (matchesPattern(domainClean, deleteConfig.patterns) && !processedSites.has(domain)) {
                            sitesToRemove.push(domain);
                        }
                    }
                    
                    for (let domain of domainsOnPage) {
                        for (let exactUrl of deleteConfig.exactUrls) {
                            const cleanExact = exactUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '');
                            if (domain.includes(cleanExact) && !processedSites.has(domain)) {
                                if (!sitesToRemove.includes(domain)) {
                                    sitesToRemove.push(domain);
                                }
                            }
                        }
                    }
                } else {
                    for (let domain of domainsOnPage) {
                        for (let siteToDelete of deleteConfig.exactUrls) {
                            const cleanSite = siteToDelete.replace(/^https?:\/\//, '').replace(/\/+$/, '');
                            if (domain.includes(cleanSite) && !processedSites.has(domain)) {
                                sitesToRemove.push(domain);
                                break;
                            }
                        }
                    }
                }

                // Если на странице больше нет сайтов для удаления - выходим из цикла
                if (sitesToRemove.length === 0) {
                    console.log(`   📌 На странице нет сайтов для удаления`);
                    hasMoreOnPage = false;
                    break;
                }

                // Удаляем ПЕРВЫЙ найденный сайт на странице
                const siteToDelete = sitesToRemove[0];
                
                try {
                    console.log(`      🗑️  ${siteToDelete}`);
                    
                    const domainClean = siteToDelete.replace(/^https?:\/\//, '').replace(/\/+$/, '');
                    const menuOpened = await findSiteRowAndClickMenu(page, domainClean);
                    
                    if (menuOpened) {
                        await new Promise(resolve => setTimeout(resolve, 500));
                        
                        const deleteClicked = await clickDeleteSiteMenuItem(page);
                        
                        if (deleteClicked) {
                            console.log(`      ✅ Удалён!`);
                            deletedOnPage++;
                            processedSites.add(siteToDelete);
                            totalDeleted++;
                            
                            // БЫСТРАЯ перезагрузка страницы
                            await page.reload({ waitUntil: 'domcontentloaded' });
                            await new Promise(resolve => setTimeout(resolve, 1000));
                            
                            // Продолжаем сканирование этой же страницы
                            continue;
                            
                        } else {
                            console.log(`      ❌ Не найден пункт "Удалить"`);
                            errorsOnPage++;
                            errorSites.push(siteToDelete);
                        }
                    } else {
                        console.log(`      ❌ Не открылось меню`);
                        errorsOnPage++;
                        errorSites.push(siteToDelete);
                    }
                } catch (error) {
                    console.log(`      ❌ Ошибка: ${error.message}`);
                    errorsOnPage++;
                    errorSites.push(siteToDelete);
                }
                
                // Если ошибка - пробуем следующий сайт
                await new Promise(resolve => setTimeout(resolve, 500));
            }

            if (deletedOnPage > 0 || errorsOnPage > 0) {
                console.log(`   📊 Удалено: ${deletedOnPage}, Ошибок: ${errorsOnPage}`);
                console.log(`   📊 Всего удалено: ${totalDeleted}\n`);
            }

            // Проверяем, все ли сайты удалены (точечный режим)
            if (deleteConfig.mode === 'exact') {
                const remainingSites = deleteConfig.exactUrls.filter(s => !processedSites.has(s));
                if (remainingSites.length === 0) {
                    console.log('✅ Все сайты удалены!');
                    break;
                }
            }

            // Переход на следующую страницу
            currentPage++;
            await new Promise(resolve => setTimeout(resolve, 1000));

        } catch (error) {
            console.log(`   ❌ Ошибка: ${error.message}`);
            currentPage++;
            continue;
        }
    }

    await browser.disconnect();

    // ===== ИТОГИ =====
    console.log('\n' + '='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log('✅ Удалено: ' + totalDeleted);
    console.log('❌ Ошибок: ' + totalErrors);
    console.log('📋 Всего записей: ' + sitesToDelete.length);
    
    const notFoundSites = [];
    if (deleteConfig.mode === 'exact') {
        for (let site of deleteConfig.exactUrls) {
            if (!processedSites.has(site)) {
                notFoundSites.push(site);
            }
        }
    }
    
    if (notFoundSites.length > 0) {
        console.log('\n🔍 НЕ НАЙДЕНЫ:');
        notFoundSites.forEach((site, i) => {
            console.log(`   ${i+1}. ${site}`);
        });
    }
    
    if (errorSites.length > 0) {
        console.log('\n🔴 ОШИБКИ:');
        errorSites.forEach((site, i) => {
            console.log(`   ${i+1}. ${site}`);
        });
    }
    
    console.log('='.repeat(70));
})();