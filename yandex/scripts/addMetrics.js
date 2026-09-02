const { loadConfig } = require('./loadConfig');
const config = loadConfig('addMetrics');
if (!config) process.exit(1);

const { links, turboPages: pages } = config;
const puppeteer = require('puppeteer');

(async () => {
    const browserURL = 'http://localhost:9229';
    const browser = await puppeteer.connect({ browserURL });

    const page = await browser.newPage();
    await new Promise(resolve => setTimeout(resolve, 500));

    // Массивы для отчета
    const successful = [];
    const failed = [];
    const errors = [];

    console.log('🚀 Запуск скрипта "Проверка метрики"');
    console.log(`📊 Всего ссылок для обработки: ${links.length}`);
    console.log('='.repeat(50));

    for (let i = 0; i < links.length; i++) {
        console.log(`\n🌐 [${i+1}/${links.length}] Обрабатываю: ${links[i]}`);

        try {
            await page.goto(`https://webmaster.yandex.ru/site/https:${links[i]}:443/indexing/crawl-metrika/`);
            await new Promise(resolve => setTimeout(resolve, 1000));

            // Горизонтальный скролл
            await page.evaluate(() => {
                const scrollContainer = document.querySelector('.ScrollableContainer-Wrapper');
                if (scrollContainer) {
                    scrollContainer.scrollLeft = scrollContainer.scrollWidth;
                }
            });
            await new Promise(resolve => setTimeout(resolve, 500));

            // Пробуем разные селекторы кнопки (тумблер)
            const buttonSelectors = [
                '.g-control-label__indicator',
                '.g-switch__indicator',
                '.tumbler__button',
                '.Toggle-Switch',
                '[role="switch"]'
            ];

            let button = null;
            for (const selector of buttonSelectors) {
                button = await page.$(selector);
                if (button) break;
            }

            if (button) {
                await button.click();
                console.log(`   ✅ Тумблер нажат`);
                
                // Ждем после нажатия
                await new Promise(resolve => setTimeout(resolve, 500));
                
                successful.push(links[i]);
            } else {
                console.log(`   ❌ Тумблер не найден`);
                failed.push(links[i]);
            }
            
        } catch (error) {
            console.log(`   ⚠️  Ошибка: ${error.message}`);
            errors.push({ link: links[i], error: error.message });
        }

        // Прогресс
        console.log(`   📊 Прогресс: ${i+1}/${links.length}`);
    }

    // ОТЧЕТ
    console.log('\n' + '='.repeat(60));
    console.log('📊 ДЕТАЛЬНЫЙ ОТЧЕТ');
    console.log('='.repeat(60));

    console.log(`\n📈 СТАТИСТИКА:`);
    console.log(`Всего ссылок: ${links.length}`);
    console.log(`✅ Успешно: ${successful.length}`);
    console.log(`❌ Не найдена кнопка: ${failed.length}`);
    console.log(`⚠️  Ошибок выполнения: ${errors.length}`);

    // ===== ОТЧЕТ ПО ОШИБКАМ =====
    if (errors.length > 0) {
        console.log('\n🔴 ССЫЛКИ С ОШИБКАМИ:');
        console.log('='.repeat(50));
        errors.forEach((err, index) => {
            console.log(`${index + 1}. ${err.link} — ${err.error}`);
        });
    }

    // ССЫЛКИ ГДЕ НЕ НАЙДЕНА КНОПКА
    if (failed.length > 0) {
        console.log('\n🚨 ССЫЛКИ ГДЕ НЕ НАЙДЕН ТУМБЛЕР:');
        console.log('='.repeat(50));
        failed.forEach((link, index) => {
            console.log(`${index + 1}. ${link}`);
        });
    }

    // УСПЕШНО ОБРАБОТАННЫЕ
    if (successful.length > 0) {
        console.log('\n✅ УСПЕШНО ОБРАБОТАННЫЕ:');
        console.log('='.repeat(50));
        successful.forEach((link, index) => {
            console.log(`${index + 1}. ${link}`);
        });
    }

    console.log('\n' + '='.repeat(60));
    console.log('🏁 СКРИПТ ЗАВЕРШЕН!');
    console.log('='.repeat(60));
})();