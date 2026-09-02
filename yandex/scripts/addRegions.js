const { loadConfig } = require('./loadConfig');
const config = loadConfig('addRegions');
if (!config) process.exit(1);

const { links, city, contactPath } = config;
const puppeteer = require('puppeteer');

(async () => {
  const browserURL = 'http://localhost:9229';
  const browser = await puppeteer.connect({ browserURL });

  const page = await browser.newPage();
  const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
  await delay(1000);

  // Массивы для отчета
  const successful = [];
  const errors = [];

  console.log('🚀 Запуск скрипта "Добавление региона"');
  console.log(`📊 Всего ссылок для обработки: ${links.length}`);
  console.log(`📁 Путь для контактов: /${contactPath}/`);
  console.log('='.repeat(50));

  for (let i = 0; i < links.length; i++) {
    console.log(`\n🌐 [${i+1}/${links.length}] Обрабатываю: ${links[i]}`);
    console.log(`   Город: ${city[i]}`);

    let errorMessage = '';

    try {
      // Переход на страницу
      await page.goto(`https://webmaster.yandex.ru/site/https:${links[i]}:443/serp-snippets/regions/`);
      await delay(3000);

      // ПЕРВАЯ КНОПКА
      try {
        await page.waitForSelector('button.g-button.g-button_view_action.g-button_size_m', { timeout: 1000 });
        const button = await page.$('button.g-button.g-button_view_action.g-button_size_m');
        
        await button.click();
        await delay(1000);
        console.log("   ✅ Первая кнопка 'Добавить регион' нажата");
        
      } catch (e) {
        errorMessage = 'Кнопка "Добавить регион" не найдена (Возможно регион был задан ранее)';
        console.log(`   ❌ ${errorMessage}`);
        errors.push({ link: links[i], error: errorMessage });
        continue;
      }

      // ВТОРАЯ КНОПКА
      const buttons2 = await page.$$('button');
      let buttonFound2 = false;

      for (let button of buttons2) {
        const buttonText = await page.evaluate(el => el.innerText, button);
        if (buttonText.includes('Добавить регион')) {
          await button.click();
          await delay(1000);
          console.log("   ✅ Вторая кнопка с текстом 'Добавить регион' нажата");
          buttonFound2 = true;
          break;
        }
      }

      if (!buttonFound2) {
        errorMessage = 'Вторая кнопка не найдена';
        console.log(`   ❌ ${errorMessage}`);
        errors.push({ link: links[i], error: errorMessage });
        continue;
      }

      // ВВОД ГОРОДА
      await delay(1500);
      const inputs = await page.$$('.g-text-input__control');
      if (inputs.length >= 2) {
        await inputs[2].type(city[i]);
        console.log(`   ✅ Введен город: ${city[i]}`);
      } else {
        errorMessage = 'Недостаточно полей ввода';
        console.log(`   ❌ ${errorMessage}`);
        errors.push({ link: links[i], error: errorMessage });
        continue;
      }

      // ВЫБОР ГОРОДА ИЗ СПИСКА
      await delay(1500);
      const selector = '.WmSuggest-Item';
      const elements = await page.$$(selector);
      let citySelected = false;

      if (elements.length > 0) {
        for (const element of elements) {
          const targetWords = city[i].split(' ');
          const text = await page.evaluate(el => el.textContent, element);
          const textWords = text.split(' ');

          const isMatch = targetWords.length === 1 ?
              textWords[0] === targetWords[0] :
              textWords[0] === targetWords[0] && textWords[1] === targetWords[1];

          if (isMatch) {
            await element.click();
            citySelected = true;
            console.log(`   ✅ Выбран город из списка: ${city[i]}`);
            break;
          }
        }
      }

      if (!citySelected) {
        errorMessage = 'Город не найден в списке';
        console.log(`   ❌ ${errorMessage}`);
        errors.push({ link: links[i], error: errorMessage });
        continue;
      }

      // ВВОД ССЫЛКИ (ИСПОЛЬЗУЕМ ПУТЬ ИЗ arr.js)
      await delay(1500);
      const contactUrl = `https://${links[i]}/${contactPath}/`;
      await inputs[3].type(contactUrl);
      console.log(`   ✅ Введена ссылка: ${contactUrl}`);

      // СОХРАНЕНИЕ
      await delay(1500);
      const buttonText = 'Сохранить';
      await page.evaluate((buttonText) => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const targetButton = buttons.find(button => button.innerText.includes(buttonText));
        if (targetButton) {
          targetButton.click();
        }
      }, buttonText);

      console.log(`   ✅ Сохранено!`);
      successful.push(links[i]);

      await delay(2000);

    } catch (error) {
      errorMessage = `Ошибка выполнения: ${error.message}`;
      console.log(`   ❌ ${errorMessage}`);
      errors.push({ link: links[i], error: errorMessage });
    }

    console.log(`   📊 Прогресс: ${i+1}/${links.length}`);
  }

  await browser.disconnect();

  // ОТЧЕТ
  console.log('\n' + '='.repeat(60));
  console.log('📊 ДЕТАЛЬНЫЙ ОТЧЕТ');
  console.log('='.repeat(60));

  console.log(`\n📈 СТАТИСТИКА:`);
  console.log(`Всего ссылок: ${links.length}`);
  console.log(`✅ Успешно: ${successful.length}`);
  console.log(`❌ С ошибками: ${errors.length}`);

  if (errors.length > 0) {
    console.log('\n🚨 ССЫЛКИ С ОШИБКАМИ:');
    console.log('='.repeat(30));
    errors.forEach((err, index) => {
      console.log(`${index + 1}. ${err.link}`);
      console.log(`   Ошибка: ${err.error}`);
    });
  }

  if (successful.length > 0) {
    console.log('\n✅ УСПЕШНО ОБРАБОТАННЫЕ:');
    console.log('='.repeat(30));
    successful.forEach((link, index) => {
      console.log(`${index + 1}. ${link}`);
    });
  }

  console.log('\n📁 ИСПОЛЬЗОВАННЫЙ ПУТЬ ДЛЯ ССЫЛОК:');
  console.log(`Формат: https://домен/${contactPath}/`);
  
  console.log('\n' + '='.repeat(60));
  console.log('🏁 СКРИПТ ЗАВЕРШЕН!');
})();