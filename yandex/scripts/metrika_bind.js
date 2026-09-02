const { loadConfig } = require('./loadConfig');
const config = loadConfig('metrika_bind');
if (!config) process.exit(1);

const { metricCounterId } = config;
const puppeteer = require('puppeteer');

(async () => {
    const browserURL = 'http://localhost:9229';
    let browser;

    console.log('🚀 ПРИВЯЗКА К ЯНДЕКС.МЕТРИКЕ (ОБХОД НЕВИДИМЫХ ФРЕЙМОВ)');
    console.log(`🔢 ID счетчика: ${metricCounterId}`);
    console.log('='.repeat(50));

    const successList = [];
    const failedList = [];
    let alreadyBoundList = [];

    try {
        browser = await puppeteer.connect({ browserURL });
        const page = await browser.newPage();
        await page.setViewport({ width: 1920, height: 1080 });

        const url = `https://metrika.yandex.ru/settings?tab=common&id=${metricCounterId}`;
        console.log(`\n🌐 Открываю страницу настроек...`);
        
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        
        console.log(`⏳ Жду 10 секунд, чтобы Яндекс успел полностью загрузить интерфейс...`);
        await new Promise(resolve => setTimeout(resolve, 10000));

        // ========== ИЩЕМ ПРАВИЛЬНЫЙ ФРЕЙМ ==========
        console.log('🕵️ Ищу, где Яндекс спрятал элементы (проверяю все фреймы)...');
        let workingFrame = null;

        for (const frame of page.frames()) {
            try {
                // Ищем те самые классы, которые вы мне скинули
                const found = await frame.evaluate(() => {
                    return !!document.querySelector('.counter-mirrors-list-item, .counter-edit__site2');
                });
                
                if (found) {
                    workingFrame = frame;
                    console.log(`✅ Нашел нужные элементы внутри фрейма!`);
                    break; // Как только нашли нужный фрейм — выходим из цикла поиска
                }
            } catch (e) {
                // Игнорируем ошибки безопасности (кросс-доменные рекламные фреймы)
            }
        }

        if (!workingFrame) {
            console.log('❌ Не удалось найти домены ни на главной странице, ни во фреймах.');
            console.log('Попробуйте запустить скрипт еще раз.');
            return;
        }

        // ========== ШАГ 1: ПОИСК УЖЕ ПРИВЯЗАННЫХ ==========
        console.log('\n🔍 Собираю список уже привязанных доменов...');
        alreadyBoundList = await workingFrame.evaluate(() => {
            const bound = [];
            const boundElements = document.querySelectorAll('.webmaster-status__action_type_delete, .webmaster-status__label');
            
            boundElements.forEach(el => {
                const wrapper = el.closest('.counter-mirrors-list-item, .counter-edit__site2, .form-fields');
                if (wrapper) {
                    const input = wrapper.querySelector('input.input__control');
                    if (input && input.value && !bound.includes(input.value)) {
                        bound.push(input.value);
                    }
                }
            });
            return bound;
        });
        console.log(`📌 Найдено уже привязанных: ${alreadyBoundList.length}`);

        // ========== ШАГ 2: КЛИКАЕМ НЕПРИВЯЗАННЫЕ ==========
        console.log('\n🎯 Начинаю прокликивать кнопки "Привязать к Вебмастеру"...');
        
        let attempts = 0;
        const maxAttempts = 1000;

        while (attempts < maxAttempts) {
            try {
                const result = await workingFrame.evaluate(() => {
                    const items = document.querySelectorAll('.counter-mirrors-list-item');
                    
                    for (const item of items) {
                        const btn = item.querySelector('button.webmaster-status__action_type_create');
                        
                        // Если кнопка есть, она активна и мы ее еще не кликали
                        if (btn && !btn.disabled && btn.dataset.clicked !== 'true') {
                            const input = item.querySelector('input.input__control');
                            const domain = input ? input.value : 'неизвестно';
                            
                            // Подтягиваем кнопку в центр экрана
                            btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            
                            // Помечаем и кликаем
                            btn.dataset.clicked = 'true';
                            btn.click();
                            
                            return { found: true, domain };
                        }
                    }
                    return { found: false };
                });

                if (result.found) {
                    successList.push(result.domain);
                    console.log(`   ✅ Нажата кнопка для: ${result.domain}`);
                    await new Promise(resolve => setTimeout(resolve, 500));
                } else {
                    // Если видимых кнопок нет — тянем экран вниз за последний элемент списка
                    const scrolled = await workingFrame.evaluate(() => {
                        const items = document.querySelectorAll('.counter-mirrors-list-item');
                        if (items.length > 0) {
                            const lastItem = items[items.length - 1];
                            const oldRect = lastItem.getBoundingClientRect().top;
                            
                            lastItem.scrollIntoView({ behavior: 'smooth', block: 'end' });
                            
                            const newRect = lastItem.getBoundingClientRect().top;
                            // Если координаты изменились, значит скролл сработал
                            return oldRect !== newRect;
                        }
                        return false;
                    });

                    if (scrolled) {
                        await new Promise(resolve => setTimeout(resolve, 1500)); // Даем время на подгрузку
                    } else {
                        break; // Дошли до самого дна, новых кнопок нет
                    }
                }
            } catch (err) {
                failedList.push({ domain: 'неизвестно', error: err.message });
                console.log(`   ⚠️ Ошибка в цикле: ${err.message}`);
                break;
            }
            attempts++;
        }

        // ========== ФИНАЛЬНЫЙ ОТЧЕТ ==========
        console.log('\n' + '='.repeat(60));
        console.log('📊 ФИНАЛЬНЫЙ ОТЧЕТ');
        console.log('='.repeat(60));

        console.log(`\n📌 УЖЕ БЫЛИ ПРИВЯЗАНЫ РАНЕЕ: ${alreadyBoundList.length}`);
        if (alreadyBoundList.length > 0) {
            alreadyBoundList.forEach((domain, i) => console.log(`   ${i+1}. ${domain}`));
        }

        console.log(`\n✅ УСПЕШНО НАЖАТО СЕЙЧАС: ${successList.length}`);
        if (successList.length > 0) {
            successList.forEach((domain, i) => console.log(`   ${i+1}. ${domain}`));
        }

        console.log(`\n❌ ОШИБКИ: ${failedList.length}`);
        if (failedList.length > 0) {
            failedList.forEach((item, i) => console.log(`   ${i+1}. ${item.domain} — ${item.error}`));
        }

        console.log('\n🏁 Скрипт успешно завершен!');

    } catch (error) {
        console.log(`\n❌ Критическая ошибка: ${error.message}`);
    } finally {
        if (browser) await browser.disconnect();
    }
})();