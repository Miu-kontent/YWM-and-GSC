const { loadConfig } = require('./loadConfig');
const config = loadConfig('Regi');
if (!config) process.exit(1);

const { links, city } = config;
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
//     console.log('✅ Данные записаны в таблицу');
//   } catch (error) {
//     console.error('❌ Ошибка записи в таблицу:', error.message);
//   }
// }

(async () => {
  let browser;
  const results = [];
  const consoleResults = [];
  const errorLinks = [];

  console.log('🚀 Запуск проверки регионов');
  console.log('============================');

  try {
    browser = await puppeteer.connect({ browserURL });
    console.log('🔗 Подключились к браузеру\n');

    // ИЗМЕНЕНИЕ 2: subdomains.length → links.length
    for (let i = 0; i < links.length; i++) {
      const page = await browser.newPage();
      // Устанавливаем ширину окна 1900px
      await page.setViewport({ width: 1900, height: 1000 });
      
      // ИЗМЕНЕНИЕ 3: subdomains[i] → links[i]
      const fullDomain = links[i].trim();
      const url = `https://webmaster.yandex.ru/site/https:${fullDomain}:443/serp-snippets/regions/`;
      
      // ИЗМЕНЕНИЕ 4: subdomains.length → links.length
      console.log(`🌐 [${i+1}/${links.length}] Проверяю: ${fullDomain}`);

      try {
        await page.goto(url, { 
          waitUntil: 'networkidle2', 
          timeout: 30000 
        });

        let foundCity = '';
        let found = false;
        
        try {
          await page.waitForSelector('ul.RegionsList.RegionsList_multiline', { timeout: 10000 });
          
          const cities = await page.$$eval('ul.RegionsList.RegionsList_multiline li.RegionsList-Item', items => 
            items.map(item => item.textContent.trim())
          );
          
          if (cities.length > 0) {
            foundCity = cities[0];
            found = true;
            console.log(`   🔍 Найден город: "${foundCity}"`);
          } else {
            console.log(`   🔍 Список найден, но города нет`);
          }
          
        } catch (error) {
          console.log(`   🔍 Элемент с городами не найден`);
        }

        let status, emoji, colorCode;
        
        // ИЗМЕНЕНИЕ 5: expectedCities[i] → city[i]
        const expectedCity = city[i];
        
        if (!found || !foundCity) {
          status = 'Нет региона';
          emoji = '❌';
          colorCode = '\x1b[31m';
          errorLinks.push({ url, reason: 'Нет региона' });
        } else if (foundCity !== expectedCity) {
          status = 'Ложь';
          emoji = '⚠️';
          colorCode = '\x1b[33m';
          errorLinks.push({ url, reason: `Ложь (ожидался: ${expectedCity}, получен: ${foundCity})` });
        } else {
          status = 'Верно';
          emoji = '✅';
          colorCode = '\x1b[32m';
        }

        const resultLine = `${fullDomain} - ${foundCity || '(пусто)'} - ${status}`;
        results.push(resultLine);
        
        console.log(`   ${emoji} ${colorCode}${resultLine}\x1b[0m`);
        consoleResults.push(`${emoji} ${resultLine}`);

      } catch (error) {
        const errorMsg = `${fullDomain} - Ошибка: ${error.message}`;
        results.push(errorMsg);
        consoleResults.push(`❌ ${errorMsg}`);
        errorLinks.push({ url, reason: `Ошибка: ${error.message}` });
        console.log(`   ❌ \x1b[31m${errorMsg}\x1b[0m`);
      } finally {
        await page.close();
      }

      await new Promise(resolve => setTimeout(resolve, 2000));
    }

    await browser.disconnect();
    console.log('\n🔌 Отключились от браузера');

    if (results.length > 0) {
      try {
        const sheets = await connectToGoogleSheets();
        await writeToSheet(sheets, results);
      } catch (error) {
        console.log('⚠️ Только консольный вывод');
      }
    }

    console.log('\n📊 ИТОГОВЫЙ ОТЧЕТ:');
    console.log('================');
    consoleResults.forEach(r => console.log(r));
    
    // ИЗМЕНЕНИЕ 6: subdomains.length → links.length
    const stats = {
      total: links.length,
      correct: results.filter(r => r.includes('Верно')).length,
      wrong: results.filter(r => r.includes('Ложь')).length,
      empty: results.filter(r => r.includes('Нет региона')).length,
      errors: results.filter(r => r.includes('Ошибка')).length
    };
    
    console.log('\n📈 СТАТИСТИКА:');
    console.log(`Всего проверок: ${stats.total}`);
    console.log(`✅ Верно: ${stats.correct}`);
    console.log(`⚠️  Ложь: ${stats.wrong}`);
    console.log(`❌ Нет региона: ${stats.empty}`);
    if (stats.errors > 0) console.log(`🔥 Ошибок: ${stats.errors}`);

    // ОТЧЕТ ОБ ОШИБКАХ НА ССЫЛКАХ
    if (errorLinks.length > 0) {
      console.log('\n🚨 ССЫЛКИ С ОШИБКАМИ:');
      console.log('====================');
      errorLinks.forEach((item, index) => {
        console.log(`\n${index + 1}. ${item.url}`);
        console.log(`   Причина: ${item.reason}`);
      });
      console.log(`\n📌 Всего проблемных ссылок: ${errorLinks.length}`);
    } else {
      console.log('\n✅ Все ссылки проверены успешно!');
    }

  } catch (error) {
    console.error('\n🔥 Критическая ошибка:', error.message);
    if (browser) await browser.disconnect();
  }
})();