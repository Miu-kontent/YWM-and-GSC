const { loadConfig } = require('./loadConfig');
const config = loadConfig('errors');
if (!config) process.exit(1);

const { links } = config;
const puppeteer = require('puppeteer');

const browserURL = 'http://localhost:9229';

const ERROR_BLOCKS_TO_CHECK = [
  {
    id: 'SLOW_AVG_RESPONSE_WITH_EXAMPLES',
    name: 'Долгий ответ сервера',
    headerText: 'Долгий ответ сервера',
    buttonXPath: '//*[@id="SLOW_AVG_RESPONSE_WITH_EXAMPLES"]/div/div[3]/button/span/span',
  },
  {
    id: 'DNS_ERROR',
    name: 'Ошибка DNS',
    headerText: 'Не удалось подключиться к серверу из-за ошибки DNS',
    buttonXPath: '//*[@id="DNS_ERROR"]/div/div[2]/button/span/span',
  },
  {
    id: 'URL_ALERT_4XX',
    name: 'Страницы с HTTP-кодом 4xx',
    headerText: 'Некоторые страницы сайта отвечают HTTP-кодом 4xx',
    buttonXPath: null
  },
  {
  id: 'CONNECT_FAILED',
  name: 'Ошибка подключения к серверу',
  headerText: 'Не удалось подключиться из-за ошибки сервера',
  buttonXPath: '//*[@id="CONNECT_FAILED"]/div/div[2]/button/span/span'
  },
];

(async () => {
  let browser;
  const domainsWithButtonsPressed = []; // Где кнопка была нажата (любая)
  const domainsWithoutButtonFound = []; // Где кнопка не найдена
  const domainsWithoutBlocks = []; // Где нет блоков
  const errorDomains = []; // Ошибки
  const domainsWithNewBlocks = []; // Сайты с новыми (неизвестными) блоками
  const uniqueNewBlockIds = new Set(); // Уникальные ID новых блоков
  
  // Детальная статистика по каждому блоку
  const blockStats = {};
  ERROR_BLOCKS_TO_CHECK.forEach(block => {
    blockStats[block.id] = {
      name: block.name,
      found: 0,
      buttonPressed: 0,
      buttonNotFound: 0,
      buttonAlreadyPressed: 0,
      domains: [] // Домены где найден этот блок
    };
  });
  
  const domainDetails = []; // Детали по каждому домену

  console.log('🚀 Проверяем блоки ошибок');
  console.log('📊 Всего ссылок для проверки:', links.length);

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
        
        await page.goto(url, { 
          waitUntil: 'networkidle2', 
          timeout: 30000 
        });
        
        await new Promise(resolve => setTimeout(resolve, 1500));

        // Подсчет всех блоков с id на странице
        const totalBlocksCount = await page.evaluate(() => {
          const container = document.querySelector('.DiagnosisChecklistErrors-ErrorsContainer');
          if (!container) return 0;
          return container.querySelectorAll('div[id]').length;
        });
        console.log(`   📊 Найдено блоков с id: ${totalBlocksCount}`);
        
        if (totalBlocksCount === 0) {
          console.log(`   ⚠️ Нет блоков с id - пропускаем`);
          domainsWithoutBlocks.push(fullDomain);
          continue;
        }

        let foundAnyBlocks = false;
        let foundAnyButtons = false;
        const domainBlocksFound = [];
        const domainBlocksNotFound = [];
        const domainErrors = []; // Ошибки найденные на этом домене

        // Проверяем каждый блок из конфигурации
        for (const block of ERROR_BLOCKS_TO_CHECK) {
          
          let blockElement = null;

          // Пробуем найти по ID (основной способ)
          if (block.id) {
            try {
              await page.waitForSelector(`#${block.id}`, { timeout: 1500 });
              blockElement = await page.$(`#${block.id}`);
            } catch {
              // Если не нашли по ID, пробуем найти внутри контейнера ошибок
              try {
                blockElement = await page.evaluateHandle((blockId) => {
                  const container = document.querySelector('.DiagnosisChecklistErrors-ErrorsContainer');
                  if (!container) return null;
                  return container.querySelector(`#${blockId}`);
                }, block.id);
              } catch {
                // Не нашли
              }
            }
          }

          // Если не нашли по ID, ищем по тексту заголовка (запасной вариант)
          if (!blockElement && block.headerText) {
            try {
              blockElement = await page.evaluateHandle((text) => {
                const elements = document.querySelectorAll('.DiagnosisChecklistErrors-ErrorsContainer .g-text.g-text_variant_header-2');
                for (const el of elements) {
                  if (el.textContent.includes(text)) {
                    // Поднимаемся до родительского блока с классом DiagnosisChecklistProblem
                    return el.closest('.DiagnosisChecklistProblem');
                  }
                }
                return null;
              }, block.headerText);
            } catch {
              // Не нашли по тексту
            }
          }

          if (!blockElement || (await page.evaluate(el => !el, blockElement))) {
            domainBlocksNotFound.push(block.name);
            continue;
          }
          
          console.log(`   🔍 Блок "${block.name}" найден`);
          foundAnyBlocks = true;
          domainBlocksFound.push(block.name);
          domainErrors.push(block.name); // Добавляем в список ошибок для этого домена
          
          // Обновляем статистику по блоку
          blockStats[block.id].found++;
          blockStats[block.id].domains.push(fullDomain);
          
          // Обработка кнопки
          if (block.buttonXPath) {
            
            let checkButton = null;
            
            try {
              checkButton = await page.evaluateHandle((xpath) => {
                const result = document.evaluate(
                  xpath,
                  document,
                  null,
                  XPathResult.FIRST_ORDERED_NODE_TYPE,
                  null
                );
                return result.singleNodeValue;
              }, block.buttonXPath);
              
            } catch (error) {
              console.log(`   ❌ Ошибка при поиске по XPath: ${error.message}`);
            }
            
            // Проверяем, есть ли кнопка
            const buttonExists = checkButton && await page.evaluate(el => !!el, checkButton);
            
            if (!buttonExists) {
              
              // Кнопки нет - проверяем, не началась ли уже проверка
              const isChecking = await page.evaluate((blockId) => {
                const block = document.getElementById(blockId);
                if (!block) return false;
                
                // Ищем статус "Проверяем сайт на ошибку"
                const statusElement = block.querySelector('.DiagnosisChecklistProblemTitle-Status');
                return statusElement && statusElement.textContent.includes('Проверяем');
              }, block.id);
              
              if (isChecking) {
                console.log(`   ✅ Проверка уже запущена (кнопка исчезла)`);
                blockStats[block.id].buttonAlreadyPressed++;
                foundAnyButtons = true;
              } else {
                console.log(`   ⚠️ Кнопка не найдена и проверка не запущена`);
                blockStats[block.id].buttonNotFound++;
              }
            } else {
              console.log(`   🔍 Кнопка найдена`);
              
              // Проверяем, не нажата ли уже кнопка
              // Поднимаемся до родительской кнопки, если нашли span
              const isDisabled = await page.evaluate((el) => {
                // Если элемент - span, ищем родительскую кнопку
                const button = el.tagName === 'BUTTON' ? el : el.closest('button');
                if (!button) return false;
                
                return button.disabled || 
                      button.classList.contains('disabled') ||
                      button.style.opacity === '0.5' ||
                      button.style.pointerEvents === 'none' ||
                      button.getAttribute('aria-disabled') === 'true';
              }, checkButton);
              
              if (isDisabled) {
                console.log(`   ✅ Кнопка уже нажата`);
                blockStats[block.id].buttonAlreadyPressed++;
                foundAnyButtons = true;
              } else {
                const buttonClicked = await clickButtonWithRetry(page, checkButton, block.id);
                
                if (buttonClicked) {
                  console.log(`   ✅ Кнопка успешно нажата!`);
                  blockStats[block.id].buttonPressed++;
                  foundAnyButtons = true;
                } else {
                  console.log(`   ❌ Не удалось нажать кнопку`);
                  blockStats[block.id].buttonNotFound++;
                }
              }
            }
          } else {
            console.log(`   📝 Блок без кнопки`);
            blockStats[block.id].buttonAlreadyPressed++;
            foundAnyButtons = true;
          }
        }

        // Проверяем наличие новых блоков
        if (totalBlocksCount > domainBlocksFound.length) {
          const newBlocksCount = totalBlocksCount - domainBlocksFound.length;
          console.log(`   ⚠️ Найдено новых блоков: ${newBlocksCount}`);
          
          // Получаем ID всех блоков на странице
          const allBlockIds = await page.evaluate(() => {
            const container = document.querySelector('.DiagnosisChecklistErrors-ErrorsContainer');
            if (!container) return [];
            const blocks = container.querySelectorAll('div[id]');
            return Array.from(blocks).map(block => block.id);
          });
          
          // Определяем известные ID из конфигурации
          const knownIds = ERROR_BLOCKS_TO_CHECK.map(b => b.id);
          
          // Находим новые ID (которых нет в knownIds)
          const newIds = allBlockIds.filter(id => !knownIds.includes(id));
          
          // Добавляем в общий Set уникальных ID
          newIds.forEach(id => uniqueNewBlockIds.add(id));
          
          domainsWithNewBlocks.push({
            domain: fullDomain,
            newBlocks: newBlocksCount,
            newIds: newIds,
            errors: domainErrors // Ошибки найденные на этом домене
          });
          
          console.log(`   🆕 Новые ID: ${newIds.join(', ')}`);
        }

        // Сохраняем детали по домену
        const domainResult = {
          domain: fullDomain,
          foundBlocks: domainBlocksFound,
          notFoundBlocks: domainBlocksNotFound,
          errors: domainErrors,
          buttonPressed: foundAnyButtons
        };
        
        domainDetails.push(domainResult);
        
        // Классифицируем результат
        if (foundAnyButtons) {
          domainsWithButtonsPressed.push(fullDomain);
        } else if (foundAnyBlocks) {
          domainsWithoutButtonFound.push(fullDomain);
        } else {
          domainsWithoutBlocks.push(fullDomain);
        }
        
      } catch (error) {
        console.log(`   ⚠️  Ошибка при обработке домена: ${error.message}`);
        errorDomains.push({ domain: fullDomain, error: error.message });
      } finally {
        if (page && !page.isClosed()) {
          await page.close().catch(() => {});
        }
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    await browser.disconnect();
    
    // ИТОГОВЫЙ ОТЧЕТ
    console.log('\n' + '='.repeat(70));
    console.log('📊 ИТОГОВЫЙ ОТЧЕТ ПО ОШИБКАМ');
    console.log('='.repeat(70));
    
    const totalChecked = links.length;
    const withButtons = domainsWithButtonsPressed.length;
    const withoutButtons = domainsWithoutButtonFound.length;
    const withoutBlocks = domainsWithoutBlocks.length;
    const withErrors = errorDomains.length;
    
    console.log(`\n📈 ОБЩАЯ СТАТИСТИКА:`);
    console.log(`✅ Проверено ссылок: ${totalChecked}`);
    console.log(`🔘 Кнопка нажата (хотя бы в одном блоке): ${withButtons}`);
    console.log(`⚠️ Кнопка не найдена (возможно нажата ранее): ${withoutButtons}`);
    console.log(`📭 Не найдено блоков для нажатия: ${withoutBlocks}`);
    if (withErrors > 0) console.log(`❌ Ошибки при проверке: ${withErrors}`);
    
    // ДЕТАЛЬНАЯ СТАТИСТИКА ПО КАЖДОМУ БЛОКУ
    console.log('\n' + '='.repeat(70));
    console.log('📊 ДЕТАЛЬНАЯ СТАТИСТИКА ПО БЛОКАМ');
    console.log('='.repeat(70));
    
    Object.values(blockStats).forEach(stat => {
      if (stat.found > 0) {
        console.log(`\n🔍 ${stat.name}:`);
        console.log(`   Найден на ${stat.found} сайтах`);
        console.log(`   Кнопка нажата сейчас: ${stat.buttonPressed}`);
        console.log(`   Кнопка уже была нажата: ${stat.buttonAlreadyPressed}`);
        console.log(`   Кнопка не найдена: ${stat.buttonNotFound}`);
      }
    });
    
    // СПИСОК САЙТОВ С ОШИБКАМИ
    console.log('\n' + '='.repeat(70));
    console.log('📋 САЙТЫ С НАЙДЕННЫМИ ОШИБКАМИ');
    console.log('='.repeat(70));
    
    const sitesWithErrors = domainDetails.filter(d => d.errors.length > 0);
    
    if (sitesWithErrors.length > 0) {
      console.log(`\n📈 Всего сайтов с ошибками: ${sitesWithErrors.length}`);
      
      sitesWithErrors.forEach((site, index) => {
        console.log(`\n${index + 1}. ${site.domain}`);
        console.log(`   Найденные ошибки: ${site.errors.join(', ')}`);
        console.log(`   Статус кнопок: ${site.buttonPressed ? '✅ нажаты' : '⚠️ не нажаты'}`);
      });
      
      // Компактный список для копирования
      console.log('\n' + '='.repeat(70));
      console.log('📝 КОМПАКТНЫЙ СПИСОК ДЛЯ КОПИРОВАНИЯ');
      console.log('='.repeat(70));
      
      sitesWithErrors.forEach(site => {
        console.log(`${site.domain} - ${site.errors.join(', ')}`);
      });
    } else {
      console.log('\n✅ Ошибки не найдены ни на одном сайте');
    }
    
    // СПИСОК САЙТОВ С НОВЫМИ БЛОКАМИ
    if (domainsWithNewBlocks.length > 0 || uniqueNewBlockIds.size > 0) {
      console.log('\n' + '='.repeat(70));
      console.log('🆕 САЙТЫ С НОВЫМИ БЛОКАМИ');
      console.log('='.repeat(70));
      
      domainsWithNewBlocks.forEach((item, index) => {
        console.log(`${index + 1}. ${item.domain} (+${item.newBlocks} новых)`);
        console.log(`   Найденные ошибки: ${item.errors.join(', ')}`);
        console.log(`   Новые ID: ${item.newIds.join(', ')}`);
      });
      
      if (uniqueNewBlockIds.size > 0) {
        console.log('\n' + '='.repeat(70));
        console.log('🔍 УНИКАЛЬНЫЕ ID НОВЫХ БЛОКОВ');
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
async function clickButtonWithRetry(page, element, blockId, maxAttempts = 3) {
  let attempts = 0;
  
  while (attempts < maxAttempts) {
    attempts++;
    
    try {
      // Кликаем по переданному элементу
      await page.evaluate((el) => {
        if (el) {
          el.click();
        }
      }, element);
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Проверяем, что кнопка исчезла или появился статус проверки
      const buttonGone = await page.evaluate((blockId) => {
        const block = document.getElementById(blockId);
        if (!block) return true;
        
        const statusElement = block.querySelector('.DiagnosisChecklistProblemTitle-Status');
        if (statusElement && statusElement.textContent.includes('Проверяем')) {
          return true;
        }
        
        const button = block.querySelector('button.DiagnosisChecklistProblemCheckButton-SubmitButton');
        return !button;
      }, blockId);
      
      if (buttonGone) {
        return true;
      }

    } catch (clickError) {
      console.log(`      ⚠️ Ошибка при клике: ${clickError.message}`);
    }
    
    if (attempts < maxAttempts) {
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  return false;
}