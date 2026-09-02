const { loadConfig } = require('./loadConfig');
const config = loadConfig('metriks');
if (!config) process.exit(1);

const { links } = config;
const puppeteer = require('puppeteer');
const { google } = require('googleapis');

const browserURL = 'http://localhost:9229';
// const SPREADSHEET_ID = '1mHmfgp9L7LAMRvAG2-zT_9g06CDuSYOSgWBYTUqt2Cs';

async function connectToGoogleSheets() {
  const auth = new google.auth.GoogleAuth({
    keyFile: 'credentials.json',
    scopes: ['https://www.googleapis.com/auth/spreadsheets'],
  });
  return google.sheets({ version: 'v4', auth });
}

// async function writeToSheet(sheets, data) {
//   try {
//     await sheets.spreadsheets.values.append({
//       spreadsheetId: SPREADSHEET_ID,
//       range: 'Лист1!A:A',
//       valueInputOption: 'RAW',
//       resource: { values: data.map(row => [row]) },
//     });
//     console.log('✅ Данные записаны');
//   } catch (error) {
//     console.error('❌ Ошибка записи:', error.message);
//   }
// }

(async () => {
  let browser;
  const results = [];
  const activatedLinks = [];
  const errors = [];

  console.log('🚀 Проверка и включение метрики');

  try {
    browser = await puppeteer.connect({ browserURL });
    
    // ИЗМЕНЕНИЕ 2: subdomains.length → links.length
    for (let i = 0; i < links.length; i++) {
      // ИЗМЕНЕНИЕ 3: subdomains[i] → links[i]
      const fullDomain = links[i].trim();
      const url = `https://webmaster.yandex.ru/site/https:${fullDomain}:443/indexing/crawl-metrika/`;
      
      // ИЗМЕНЕНИЕ 4: subdomains.length → links.length
      console.log(`\n🌐 [${i+1}/${links.length}] ${fullDomain}`);

      let page;
      try {
        page = await browser.newPage();
        await page.setViewport({ width: 1900, height: 1000 });
        
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        // Проверяем текущее состояние
        const initialState = await checkMetricState(page);
        
        if (initialState === 'error') {
          console.log('   ❌ Не найден переключатель');
          errors.push(`${fullDomain} - Элемент не найден`);
          results.push(`${fullDomain} - Элемент не найден`);
          await page.close();
          continue;
        }
        
        console.log(`   📊 Начальное состояние: ${initialState}`);
        
        // Если метрика выключена - включаем
        if (initialState === 'disabled') {
          console.log('   🔘 Включаю метрику...');
          
          // Ищем переключатель через CSS-селектор
          const switchButton = await page.$('input.g-switch__control[role="switch"]') || 
                               await page.$('label.g-switch');
          
          if (switchButton) {
            await switchButton.click();
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Проверяем новое состояние
            const newState = await checkMetricState(page);
            console.log(`   📊 Новое состояние: ${newState}`);
            
            if (newState === 'enabled') {
              activatedLinks.push(fullDomain);
              results.push(`${fullDomain} - Активировано`);
            } else {
              errors.push(`${fullDomain} - Не удалось активировать`);
              results.push(`${fullDomain} - Ошибка активации`);
            }
          } else {
            console.log('   ❌ Не найден элемент для клика');
            errors.push(`${fullDomain} - Не найден элемент`);
            results.push(`${fullDomain} - Элемент не найден`);
          }
        } else {
          results.push(`${fullDomain} - Уже включено`);
          console.log(`   ✅ Уже включено`);
        }

      } catch (error) {
        console.log(`   ⚠️  Ошибка: ${error.message}`);
        errors.push(`${fullDomain} - ${error.message}`);
        results.push(`${fullDomain} - Ошибка`);
      } finally {
        if (page && !page.isClosed()) {
          await page.close().catch(() => {});
        }
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    await browser.disconnect();
    
    // Запись в таблицу
    if (results.length > 0) {
      try {
        const sheets = await connectToGoogleSheets();
        await writeToSheet(sheets, results);
      } catch (error) {
        console.log('⚠️ Только консольный вывод');
      }
    }

    // Краткий отчет
    // ИЗМЕНЕНИЕ 5: subdomains.length → links.length
    console.log('\n📊 ИТОГИ:');
    console.log(`Проверено: ${links.length}`);
    console.log(`✅ Уже включено: ${links.length - activatedLinks.length - errors.length}`);
    console.log(`🔄 Активировано: ${activatedLinks.length}`);
    console.log(`❌ Ошибок: ${errors.length}`);
    
    if (activatedLinks.length > 0) {
      console.log('\n🔄 Активированы:');
      activatedLinks.forEach(link => console.log(`  • ${link}`));
    }
    
    if (errors.length > 0) {
      console.log('\n❌ Ошибки (первые 10):');
      errors.slice(0, 10).forEach(error => console.log(`  • ${error}`));
      if (errors.length > 10) console.log(`  ... и еще ${errors.length - 10} ошибок`);
    }

  } catch (error) {
    console.error('\n🔥 Критическая ошибка:', error.message);
    if (browser) await browser.disconnect().catch(() => {});
  }
})();

async function checkMetricState(page) {
  try {
    await page.waitForSelector('input.g-switch__control[role="switch"]', { timeout: 10000 });
    
    const isEnabled = await page.$eval('input.g-switch__control[role="switch"]', input => {
      return input.getAttribute('aria-checked') === 'true';
    });
    
    return isEnabled ? 'enabled' : 'disabled';
  } catch {
    return 'error';
  }
}