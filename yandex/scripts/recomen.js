const { loadConfig } = require('./loadConfig');
const config = loadConfig('recomen');
if (!config) process.exit(1);

const { links } = config;
const puppeteer = require('puppeteer');

const browserURL = 'http://localhost:9229';

// Конфигурация блоков для проверки
const BLOCKS_TO_CHECK = [
  {
    id: 'SLOW_AVG_RESPONSE_WITH_EXAMPLES',
    name: 'Долгий ответ сервера',
    headerText: 'Долгий ответ сервера',
    xpath: '//*[@id="SLOW_AVG_RESPONSE_WITH_EXAMPLES"]/div/div[1]/span[1]',
    buttonXPath: '//*[@id="SLOW_AVG_RESPONSE_WITH_EXAMPLES"]/div/div[3]/button/span/span'
  },
  {
    id: 'NO_DICTIONARY_REGIONS',
    name: 'Рекомендация',
    headerText: 'Добавьте сайт вашей организации в Яндекс Бизнес',
    xpath: null,
    buttonXPath: '//*[@id="NO_DICTIONARY_REGIONS"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'
  },
  {
    id: 'ERRORS_IN_SITEMAPS',
    name: 'Ошибки Sitemap',
    headerText: 'Обнаружены ошибки в файлах Sitemap',
    xpath: '//*[@id="ERRORS_IN_SITEMAPS"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: null
  },
  
  // Новое
  {
    id: 'SITEMAP_NOT_SET',
    name: 'Нет используемых роботом файлов Sitemap',
    headerText: 'Нет используемых роботом файлов Sitemap',
    xpath: '//*[@id="SITEMAP_NOT_SET"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="SITEMAP_NOT_SET"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'    
  },
  {
    id: 'NO_REGIONS',
    name: 'Укажите регион вашего сайта — это может влиять на его позицию в поиске по запросам пользователей в зависимости от их местоположения',
    headerText: 'Укажите регион вашего сайта — это может влиять на его позицию в поиске по запросам пользователей в зависимости от их местоположения',
    xpath: '//*[@id="NO_REGIONS"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="NO_REGIONS"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'    
  },
  {
    id: 'DOCUMENTS_MISSING_DESCRIPTION',
    name: 'Отсутствуют метатеги <Description>',
    headerText: 'Отсутствуют метатеги <Description>',
    xpath: '//*[@id="DOCUMENTS_MISSING_DESCRIPTION"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="DOCUMENTS_MISSING_DESCRIPTION"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'    
  },
  {
    id: 'DOCUMENTS_MISSING_TITLE',
    name: 'Отсутствуют метатеги <title>',
    headerText: 'Отсутствуют метатеги <title>',
    xpath: '//*[@id="DOCUMENTS_MISSING_TITLE"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="DOCUMENTS_MISSING_TITLE"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'    
  },
// Конец Новое

// NORMAL NEW
  {
    id: 'MISSING_FAVICON',
    name: 'Файл favicon не найден',
    headerText: 'Файл favicon не найден',
    xpath: '//*[@id="MISSING_FAVICON"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="MISSING_FAVICON"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'
  },
  {
    id: 'NO_404_ERRORS',
    name: 'Некорректно настроено отображение несуществующих файлов и страниц',
    headerText: 'Некорректно настроено отображение несуществующих файлов и страниц',
    xpath: '//*[@id="NO_404_ERRORS"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="NO_404_ERRORS"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'    
  },
  {
    id: 'BIG_FAVICON_ABSENT', //Без кнопки просто рекомендация
    name: 'Добавьте файл favicon в формате SVG или размером 120 × 120 пикселей',
    headerText: 'Добавьте файл favicon в формате SVG или размером 120 × 120 пикселей',
    xpath: null,
    buttonXPath: null
  },
  {
    id: 'NO_METRIKA_COUNTER_CRAWL_ENABLED',
    name: 'Не включён обход по счётчикам',
    headerText: 'Не включён обход по счётчикам',
    xpath: null,
    buttonXPath: null
  },
  {
    id: 'NO_METRIKA_COUNTER_BINDING',
    name: 'Счётчик Яндекс Метрики не привязан к сайту',
    headerText: 'Счётчик Яндекс Метрики не привязан к сайту',
    xpath: null,
    buttonXPath: null
  },
  {
    id: 'TOO_MANY_DOMAINS_ON_SEARCH', //Без кнопки просто уведомление о большом колличестве сайтов
    name: 'В результатах поиска найдены поддомены сайта',
    headerText: 'В результатах поиска найдены поддомены сайта',
    xpath: null,
    buttonXPath: null
  },
  {
    id: 'NOT_MOBILE_FRIENDLY',
    name: 'Сайт не оптимизирован для мобильных устройств',
    headerText: 'Сайт не оптимизирован для мобильных устройств',
    xpath: '//*[@id="NOT_MOBILE_FRIENDLY"]/div/div[1]/div/div/div/span[1]',
    buttonXPath: '//*[@id="NOT_MOBILE_FRIENDLY"]/div/div[2]/div/div/div/div/div/div[2]/button/span/span'
  },
  
// END
];

(async () => {
  let browser;
  const domainsWithButtonsPressed = []; // Где кнопка была нажата (любая)
  const domainsWithoutButtonFound = []; // Где кнопка не найдена
  const domainsWithoutBlocks = []; // Где нет блоков
  const errorDomains = []; // Ошибки
  // Новое
  const domainsWithNewBlocks = [];
  const uniqueNewBlockIds = new Set();
  // Конец новое

  // === ДОРАБОТКА (Итоговый вывод для уведомлений) ===
  const noMetrikaCrawlDomains = [];
  const noMetrikaBindingDomains = [];

  // Отдельные массивы для 4-го блока
  const slowResponseDomainsFound = []; // Домены где найден блок "Долгий ответ"
  const slowResponseDomainsPressed = []; // Домены где кнопка в этом блоке нажата
  const slowResponseDomainsFailed = []; // Домены где блок найден, но кнопку нажать не удалось
  
  const domainDetails = []; // Детали по каждому домену

  console.log('🚀 Проверяем блоки...');

  try {
    browser = await puppeteer.connect({ 
      browserURL: browserURL,
      defaultViewport: null 
    });
    
    for (let i = 0; i < links.length; i++) {
      const fullDomain = links[i].trim();
      const url = `https://webmaster.yandex.ru/site/https:${fullDomain}:443/optimization/checklist/`;
      
      console.log(`\n🌐 [${i+1}/${links.length}] ${fullDomain}`);

      let page;
      try {
        page = await browser.newPage();
        await page.setViewport({ width: 1900, height: 1000 });
        
        console.log(`   📍 Перехожу на страницу...`);
        await page.goto(url, { 
          waitUntil: 'networkidle2', 
          timeout: 30000 
        });
        
        await new Promise(resolve => setTimeout(resolve, 1500));

      	const totalBlocksCount = await page.evaluate(() => {
          // Ищем элемент по ID секции и классу заголовка (это надежнее, чем длинный XPath)
          const titleSpan = document.querySelector('#RECOMMENDATION .DiagnosisChecklistAccordion-Title');
          
          if (titleSpan && titleSpan.textContent) {
            // Ищем в строке (например, "Рекомендации  • 4") первое совпадение с цифрами
            const match = titleSpan.textContent.match(/\d+/);
            
            if (match) {
              return parseInt(match[0], 10);
            }
          }
          
          return 0; // Возвращаем 0, если элемент не найден или в нем нет цифр
        });
        console.log(`   📊 Найдено блоков с id: ${totalBlocksCount}`);
        
        if (totalBlocksCount === 0) {
          console.log(`   ⚠️ Нет блоков с id - пропускаем`);
        domainsWithoutBlocks.push(fullDomain);
        continue;
        }

        // === ДОРАБОТКА 1: Нажатие "Показать все", если блоков больше 3 ===
        if (totalBlocksCount > 3) {
          console.log(`   🗂️ Блоков больше 3 (${totalBlocksCount}), пытаюсь раскрыть весь список...`);
          try {
            const showAllXPath = '//*[@id="RECOMMENDATION"]/div/div[2]/div/div/div/button/span[2]/span'; 
            
            const showAllClicked = await page.evaluate((xpath) => {
              // Попытка 1: Ищем по XPath
              try {
                const btnNode = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                if (btnNode) { 
                  btnNode.click(); 
                  return true; 
                }
              } catch(e) {}
              
              // Попытка 2: Умный поиск по тексту
              const elements = Array.from(document.querySelectorAll('button, span, div, a'));
              const showAllBtn = elements.find(el => {
                const text = el.textContent.trim().toLowerCase();
                return text === 'Посмотреть все';
              });
              
              if (showAllBtn) {
                showAllBtn.click();
                return true;
              }
              return false;
            }, showAllXPath);

            if (showAllClicked) {
              console.log(`   ✅ Кнопка раскрытия списка нажата! Ожидаю изменения текста на "Свернуть"...`);
              
              // Ждем, пока список физически раскроется и текст кнопки изменится
              const isExpanded = await page.evaluate(async () => {
                return new Promise((resolve) => {
                  let attempts = 0;
                  const interval = setInterval(() => {
                    attempts++;
                    const elements = Array.from(document.querySelectorAll('button, span, div, a'));
                    const collapseBtn = elements.find(el => el.textContent.trim().toLowerCase() === 'свернуть');
            
                    if (collapseBtn) {
                      clearInterval(interval);
                      resolve(true); // Успешно раскрылось
                    } else if (attempts >= 10) { // Ждем максимум 5 секунд (10 попыток * 500мс)
                      clearInterval(interval);
                      resolve(false); // Не дождались изменения текста
                    }
                  }, 500);
                });
              });

          if (isExpanded) {
                console.log(`   ✅ Список успешно раскрыт (появилась кнопка "Свернуть")!`);
          } else {
                console.log(`   ⚠️ Кнопка нажималась, но текст "Свернуть" не появился. Возможно, список уже был раскрыт или не успел прогрузиться.`);
              }
              
              await new Promise(resolve => setTimeout(resolve, 1000)); // Небольшая пауза для стабилизации DOM
            } else {
              console.log(`   ⚠️ Кнопка "Посмотреть все" не найдена ни по XPath, ни по тексту. Скрипт продолжит работу.`);
            }
          } catch (err) {
            console.log(`   ❌ Ошибка при попытке нажать "Посмотреть все": ${err.message}`);
          }
        }
        // ===================================================================

        let foundAnyBlocks = false;
        let foundAnyButtons = false;
        const domainBlocksFound = [];
        const domainBlocksNotFound = [];
        
        let slowResponseFound = false;
        let slowResponseButtonPressed = false;
        
        for (const block of BLOCKS_TO_CHECK) {
          console.log(`   🔍 Ищу блок "${block.name}"...`);
          
          let blockElement = null;
          
          // Пробуем разные способы найти блок
          if (block.id) {
            try {
              await page.waitForSelector(`#${block.id}`, { timeout: 1500 });
              blockElement = await page.$(`#${block.id}`);
            } catch {}
          }
          
          // Если не нашли по ID, пробуем по XPath
          if (!blockElement && block.xpath) {
            try {
              blockElement = await page.evaluateHandle((xpath) => {
                const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return result.singleNodeValue;
              }, block.xpath);
            } catch {}
          }
          
          // Если не нашли по XPath, ищем по тексту заголовка
          if (!blockElement && block.headerText) {
            try {
              blockElement = await page.evaluateHandle((text) => {
                const elements = document.querySelectorAll('span.g-text.g-text_variant_header-1, span.g-text.g-text_variant_header-2');
                for (const el of elements) {
                  if (el.textContent.includes(text)) {
                    let parent = el;
                    while (parent && !parent.id) {
                      parent = parent.parentElement;
                    }
                    return parent || el.closest('.DiagnosisChecklistProblem') || el;
                  }
                }
                return null;
              }, block.headerText);
            } catch {}
          }
          
          if (!blockElement || (await page.evaluate(el => !el, blockElement))) {
            console.log(`   ⚠️  Блок "${block.name}" не найден`);
            domainBlocksNotFound.push(block.name);
            continue; // Переходим к следующему блоку
          }
          
          console.log(`   ✅ Блок "${block.name}" найден...`);
          foundAnyBlocks = true;
          domainBlocksFound.push(block.name);
          
          if (block.id === 'SLOW_AVG_RESPONSE_WITH_EXAMPLES') {
            slowResponseFound = true;
            slowResponseDomainsFound.push(fullDomain);
          }
          
          // === ДОРАБОТКА 3: Блоки-уведомления (без кнопок) ===
          if (['NO_METRIKA_COUNTER_CRAWL_ENABLED', 'NO_METRIKA_COUNTER_BINDING'].includes(block.id)) {
            console.log(`   ℹ️ Блок является уведомлением. Сохраняю для итогового отчета и пропускаю клик...`);
            
            if (block.id === 'NO_METRIKA_COUNTER_CRAWL_ENABLED') {
              noMetrikaCrawlDomains.push(fullDomain);
            } else if (block.id === 'NO_METRIKA_COUNTER_BINDING') {
              noMetrikaBindingDomains.push(fullDomain);
            }

            // Проверка на ранний выход (если это был последний блок на странице)
            if (domainBlocksFound.length >= totalBlocksCount) {
              console.log(`   🏁 Найдено и обработано нужное количество блоков (${totalBlocksCount}). Иду к следующему сайту...`);
              break; 
            }
            continue; 
          }
          // ===================================================
          
          try {
            await page.evaluate((el) => {
              const clickable = el.querySelector('.Accordion-Header') || 
                              el.querySelector('.DiagnosisChecklistProblem') || el;
              if (clickable) clickable.click();
            }, blockElement);
            
            await new Promise(resolve => setTimeout(resolve, 1500));
            
            // Ищем кнопку "Проверить" внутри открытого блока
            console.log(`   🔍 Ищу кнопку "Проверить" в блоке "${block.name}"...`);
            let checkButton = null;
            
            // Сначала пробуем найти по XPath
            if (block.buttonXPath) {
              try {
                checkButton = await page.evaluateHandle((xpath) => {
                  const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                  return result.singleNodeValue;
                }, block.buttonXPath);
              } catch {}
            }
            
            // Если нет XPath или не нашли, ищем внутри блока
            if (!checkButton || (await page.evaluate(el => !el, checkButton))) {
              checkButton = await page.evaluateHandle((blockId) => {
                const blockEl = document.getElementById(blockId);
                if (!blockEl) return null;
                
                // Ищем кнопку по классу внутри блока
                const btnByClass = blockEl.querySelector('button.DiagnosisChecklistProblemCheckButton-SubmitButton');
                if (btnByClass) return btnByClass;
                
                // Ищем по тексту "Проверить" внутри блока
                const buttons = blockEl.querySelectorAll('button');
                for (const btn of buttons) {
                  if (btn.textContent.includes('Проверить')) return btn;
                }
                return null;
              }, block.id);
            }
            
            // Если все еще не нашли, ищем на всей странице
            if (!checkButton || (await page.evaluate(el => !el, checkButton))) {
              checkButton = await page.evaluateHandle(() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                  if (btn.textContent.includes('Проверить')) return btn;
                }
                return null;
              });
            }
            
            if (!checkButton || (await page.evaluate(el => !el, checkButton))) {
              console.log(`   ⚠️  Кнопка в блоке "${block.name}" не найдена`);
              if (block.id === 'SLOW_AVG_RESPONSE_WITH_EXAMPLES') slowResponseDomainsFailed.push(fullDomain);
            } else {
            console.log(`   ✅ Кнопка найдена, нажимаю...`);
            
            // Нажимаем кнопку
            const buttonClicked = await clickButtonWithRetry(page, checkButton);
            
            if (buttonClicked) {
              console.log(`   ✅ Кнопка в блоке "${block.name}" успешно нажата!`);
              foundAnyButtons = true;
              
              // Особый случай для блока "Долгий ответ сервера"
              if (block.id === 'SLOW_AVG_RESPONSE_WITH_EXAMPLES') {
                slowResponseButtonPressed = true;
                slowResponseDomainsPressed.push(fullDomain);
              }
              
            } else {
              console.log(`   ❌ Не удалось нажать кнопку в блоке "${block.name}"`);
                if (block.id === 'SLOW_AVG_RESPONSE_WITH_EXAMPLES') slowResponseDomainsFailed.push(fullDomain);
              }
            }
            
          } catch (blockError) {
            console.log(`   ❌ Ошибка при обработке блока "${block.name}": ${blockError.message}`);
            if (block.id === 'SLOW_AVG_RESPONSE_WITH_EXAMPLES') slowResponseDomainsFailed.push(fullDomain);
            }

          // === ДОРАБОТКА 2: Ранний выход ===
          if (domainBlocksFound.length >= totalBlocksCount) {
            console.log(`   🏁 Найдено и обработано нужное количество блоков (${totalBlocksCount}). Иду к следующему сайту...`);
            break; // Выходим из цикла поиска блоков, так как всё нужное уже нашли
          }
          // ==================================
        }

        if (totalBlocksCount > domainBlocksFound.length) {
          const newBlocksCount = totalBlocksCount - domainBlocksFound.length;
            console.log(`   ⚠️ Найдено новых блоков: ${newBlocksCount}`);
          const allBlockIds = await page.evaluate(() => {
          const container = document.querySelector('.DiagnosisChecklistAccordion-Content');
          if (!container) return [];
              return Array.from(container.querySelectorAll('div[id]')).map(block => block.id);
          });
          const knownIds = BLOCKS_TO_CHECK.map(b => b.id);
          const newIds = allBlockIds.filter(id => !knownIds.includes(id));
          newIds.forEach(id => uniqueNewBlockIds.add(id));
          domainsWithNewBlocks.push({ domain: fullDomain, newBlocks: newBlocksCount, newIds: newIds });
          console.log(`   🆕 Новые ID: ${newIds.join(', ')}`);
        }
        
        const domainResult = {
          domain: fullDomain,
          foundBlocks: domainBlocksFound,
          notFoundBlocks: domainBlocksNotFound,
          buttonPressed: foundAnyButtons,
          slowResponseFound: slowResponseFound,
          slowResponseButtonPressed: slowResponseButtonPressed
        };
        
        domainDetails.push(domainResult);
        
        if (foundAnyButtons) domainsWithButtonsPressed.push(fullDomain);
        else if (foundAnyBlocks) domainsWithoutButtonFound.push(fullDomain);
        else domainsWithoutBlocks.push(fullDomain);
        
      } catch (error) {
        console.log(`   ⚠️  Ошибка при обработке домена: ${error.message}`);
        errorDomains.push({ domain: fullDomain, error: error.message });
      } finally {
        if (page && !page.isClosed()) await page.close().catch(() => {});
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    await browser.disconnect();
    
    // ИТОГОВЫЙ ОТЧЕТ
    console.log('\n' + '='.repeat(70));
    console.log('📊 ИТОГОВЫЙ ОТЧЕТ');
    console.log('='.repeat(70));
    
    const totalChecked = links.length;
    
    console.log(`\n📈 ОБЩАЯ СТАТИСТИКА:`);
    console.log(`${totalChecked} ссылок проверено`);
    console.log(`${domainsWithButtonsPressed.length} ссылок - кнопка "Проверить" нажата (хотя бы в одном блоке)`);
    console.log(`${domainsWithoutButtonFound.length} ссылок - кнопка не найдена (возможно была нажата ранее или блок - уведомление)`);
    console.log(`${domainsWithoutBlocks.length} ссылок - не найдено блоков для нажатия`);
    if (errorDomains.length > 0) console.log(`${errorDomains.length} ссылок - ошибки при проверке`);
    
    // === ДОРАБОТКА 3: Вывод уведомлений ===
    if (noMetrikaCrawlDomains.length > 0) {
      console.log('\n' + '='.repeat(70));
      console.log('📌 УВЕДОМЛЕНИЕ: Не включён обход по счётчикам (NO_METRIKA_COUNTER_CRAWL_ENABLED)');
      console.log('='.repeat(70));
      noMetrikaCrawlDomains.forEach((domain, index) => {
        console.log(`${index + 1}. ${domain}`);
      });
    }

    if (noMetrikaBindingDomains.length > 0) {
      console.log('\n' + '='.repeat(70));
      console.log('📌 УВЕДОМЛЕНИЕ: Счётчик Яндекс Метрики не привязан (NO_METRIKA_COUNTER_BINDING)');
      console.log('='.repeat(70));
      noMetrikaBindingDomains.forEach((domain, index) => {
        console.log(`${index + 1}. ${domain}`);
      });
    }
    // ======================================

    console.log('\n' + '='.repeat(70));
    console.log('📊 ОТЧЕТ ПО БЛОКУ "ДОЛГИЙ ОТВЕТ СЕРВЕРА"');
    console.log('='.repeat(70));
    
    console.log(`\n📈 СТАТИСТИКА ПО БЛОКУ:`);
    console.log(`Найдено на ${slowResponseDomainsFound.length} из ${totalChecked} ссылок`);
    console.log(`Успешно нажата кнопка на ${slowResponseDomainsPressed.length} ссылках`);
    console.log(`Не удалось нажать кнопку на ${slowResponseDomainsFailed.length} ссылках`);
    
    // Список ссылок где найден блок "Долгий ответ сервера"
    if (slowResponseDomainsFound.length > 0) {
      console.log(`\n✅ ССЫЛКИ ГДЕ НАЙДЕН БЛОК "ДОЛГИЙ ОТВЕТ СЕРВЕРА":`);
      console.log('='.repeat(50));
      slowResponseDomainsFound.forEach((domain, index) => {
        const details = domainDetails.find(d => d.domain === domain);
        const buttonStatus = details?.slowResponseButtonPressed ? '✅ НАЖАТА' : '❌ НЕ НАЖАТА';
        console.log(`${index + 1}. ${domain} - ${buttonStatus}`);
      });
    }
    
    // Список где кнопка успешно нажата
    if (slowResponseDomainsPressed.length > 0) {
      console.log(`\n🎯 ССЫЛКИ ГДЕ КНОПКА В ЭТОМ БЛОКЕ УСПЕШНО НАЖАТА:`);
      slowResponseDomainsPressed.forEach((domain, index) => {
        console.log(`${index + 1}. ${domain}`);
      });
    }
    
    // Список где не удалось нажать
    if (slowResponseDomainsFailed.length > 0) {
      console.log(`\n⚠️  ССЫЛКИ ГДЕ НЕ УДАЛОСЬ НАЖАТЬ КНОПКУ В ЭТОМ БЛОКЕ:`);
      slowResponseDomainsFailed.slice(0, 10).forEach((domain, index) => {
        console.log(`${index + 1}. ${domain}`);
      });
      if (slowResponseDomainsFailed.length > 10) {
        console.log(`   ... и еще ${slowResponseDomainsFailed.length - 10}`);
      }
    }
    
    // Общий список где не была нажата кнопка "Проверить"
    if (domainsWithoutButtonFound.length > 0) {
      console.log(`\n🚨 ССЫЛКИ ГДЕ КНОПКА "ПРОВЕРИТЬ" НЕ БЫЛА НАЖАТА:`);
      console.log('='.repeat(50));
      domainsWithoutButtonFound.slice(0, 10).forEach((domain, index) => {
        const details = domainDetails.find(d => d.domain === domain);
        console.log(`${index + 1}. ${domain}`);
        console.log(`   Найдено блоков: ${details?.foundBlocks?.join(', ') || 'нет'}`);
        console.log(`   Не найдено блоков: ${details?.notFoundBlocks?.join(', ') || 'нет'}`);
      });
      if (domainsWithoutButtonFound.length > 10) {
        console.log(`   ... и еще ${domainsWithoutButtonFound.length - 10}`);
      }
    }

  if (domainsWithNewBlocks.length > 0 || uniqueNewBlockIds.size > 0) {
  console.log('\n' + '='.repeat(70));
  console.log('🆕 САЙТЫ С НОВЫМИ БЛОКАМИ');
  console.log('='.repeat(70));
  domainsWithNewBlocks.forEach((item, index) => {
  console.log(`${index + 1}. ${item.domain} (+${item.newBlocks} новых) - ID: ${item.newIds.join(', ')}`);
  });
  if (uniqueNewBlockIds.size > 0) {
  console.log('\n' + '='.repeat(70));
  console.log('🔍 УНИКАЛЬНЫЕ ID НОВЫХ БЛОКОВ (для добавления в BLOCKS_TO_CHECK)');
  console.log('='.repeat(70));
  console.log(`\n📊 Всего уникальных новых блоков: ${uniqueNewBlockIds.size}`);
  const uniqueIdsArray = Array.from(uniqueNewBlockIds).sort();
  uniqueIdsArray.forEach((id, index) => {
  console.log(`${index + 1}. ${id}`);
  });
  }
 console.log(`\n📊 Всего сайтов с новыми блоками: ${domainsWithNewBlocks.length}`);
 }

  } catch (error) {
    console.error('\n🔥 Критическая ошибка:', error.message);
    if (browser) await browser.disconnect().catch(() => {});
  }
})();

// Функция для нажатия кнопки с повторами
async function clickButtonWithRetry(page, buttonElement, maxAttempts = 3) {
  let attempts = 0;
  
  while (attempts < maxAttempts) {
    attempts++;
    try {
      await page.evaluate((btn) => {
        if (btn) btn.click();
      }, buttonElement);
      
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      // Проверяем результат
      const buttonStillActive = await page.evaluate(() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
          if (btn.textContent.includes('Проверить')) {
            return !(btn.disabled || 
                    btn.classList.contains('disabled') ||
                    btn.style.opacity === '0.5' ||
                    btn.style.pointerEvents === 'none');
          }
        }
        return false;
      });
      
      if (!buttonStillActive) {
        return true;
      }
      
    } catch (clickError) {}
    
    if (attempts < maxAttempts) {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  
  return false;
}