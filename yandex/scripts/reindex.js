const { loadConfig } = require('./loadConfig');
const puppeteer = require('puppeteer');

function getLinksFromConfig() {
    const config = loadConfig('reindex');
    if (!config) return [];
    
    const links = config.links || [];
    console.log(`✅ Загружено ${links.length} доменов`);
    return links;
}

// =============================================================================
// ПЕРЕОБХОД СТРАНИЦ - КАК БЫЛО +15% СКОРОСТИ
// =============================================================================

async function automateYandexWebmaster() {
    console.log('='.repeat(70));
    console.log('🚀 ЗАПУСК СКРИПТА: Переобход Страниц в Яндекс Вебмастер');
    console.log('='.repeat(70));
    console.log();
    
    const domains = getLinksFromConfig();
    if (domains.length === 0) {
        console.log('❌ Нет доменов для обработки!');
        return;
    }
    
    console.log(`📊 Всего доменов: ${domains.length}`);
    console.log();
    
    // Формируем URL
    const urlsArray = domains.map(domain => `https://${domain}`);
    
    console.log('🔍 Подключаюсь к Chrome...');
    console.log('   chrome.exe --remote-debugging-port=9229 --user-data-dir="C:\\chrome-debug"');
    console.log();
    
    let browser;
    try {
        browser = await puppeteer.connect({
            browserURL: 'http://localhost:9229',
            defaultViewport: null
        });
        console.log('✅ Подключение к Chrome установлено');
        console.log();
    } catch (error) {
        console.log('❌ Ошибка подключения к Chrome!');
        return;
    }
    
    const pages = await browser.pages();
    const page = pages[0] || await browser.newPage();
    
    // Стандартный таймаут
    await page.setDefaultNavigationTimeout(30000);
    
    let success = 0;
    let errors = 0;
    
    // Обрабатываем домены последовательно - КАК БЫЛО
    for (let i = 0; i < domains.length; i++) {
        const domain = domains[i];
        const url = urlsArray[i];
        const webmasterUrl = `https://webmaster.yandex.ru/site/https:${domain}:443/indexing/reindex/`;
        
        console.log(`${i + 1}/${domains.length}: ${domain}`);
        
        try {
            await page.goto(webmasterUrl, { 
                waitUntil: 'networkidle2',  // КАК БЫЛО
                timeout: 30000 
            });
            
            // Задержка после загрузки страницы - УМЕНЬШЕНА НА 15%
            await new Promise(resolve => setTimeout(resolve, 1700)); // Было 2000, стало 1700
            
            try {
                await page.waitForSelector('textarea.g-text-area__control', {timeout: 15000});
                
                const textarea = await page.$('textarea.g-text-area__control');
                
                await textarea.click({clickCount: 3});
                await page.keyboard.press('Backspace');
                
                // Скорость ввода - УВЕЛИЧЕНА НА 15%
                await textarea.type(url, {delay: 43}); // Было 50, стало 43
                
                // Задержка перед нажатием кнопки - УМЕНЬШЕНА НА 15%
                await new Promise(resolve => setTimeout(resolve, 850)); // Было 1000, стало 850
                
                const submitButton = await page.$('button.g-button');
                if (submitButton) {
                    await submitButton.click();
                    console.log(`   ✅ Переобход запущен`);
                    success++;
                } else {
                    console.log(`   ❌ Кнопка не найдена`);
                    errors++;
                }
                
                // Задержка перед следующим доменом - УМЕНЬШЕНА НА 15%
                await new Promise(resolve => setTimeout(resolve, 2550)); // Было 3000, стало 2550
                
            } catch (error) {
                console.log(`   ❌ Ошибка на странице: ${error.message.slice(0, 50)}`);
                errors++;
            }
            
        } catch (error) {
            console.log(`   ❌ Ошибка загрузки страницы: ${error.message.slice(0, 50)}`);
            errors++;
        }
    }
    
    await browser.disconnect();
    
    console.log();
    console.log('='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log(`✅ Успешно: ${success}`);
    console.log(`❌ Ошибок: ${errors}`);
    console.log(`📋 Всего: ${domains.length}`);
    console.log('='.repeat(70));
}

automateYandexWebmaster().catch(error => {
    console.log('❌ КРИТИЧЕСКАЯ ОШИБКА:', error.message);
});