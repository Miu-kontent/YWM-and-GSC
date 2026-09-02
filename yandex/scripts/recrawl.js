const { loadConfig } = require('./loadConfig');
const config = loadConfig('recrawl');
if (!config) process.exit(1);

const { links } = config;
const puppeteer = require('puppeteer');

(async () => {
  try {
    const browserURL = 'http://localhost:9229';
    const browser = await puppeteer.connect({ browserURL });
    const page = await browser.newPage();
    
    // ===== УСТАНАВЛИВАЕМ РАЗМЕР ОКНА ПОД ЭКРАН =====
    const dimensions = await page.evaluate(() => {
      return {
        width: window.screen.width,
        height: window.screen.height
      };
    });
    
    await page.setViewport({
      width: dimensions.width,
      height: dimensions.height
    });
    
    const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    console.log('='.repeat(70));
    console.log('🚀 ЗАПУСК СКРИПТА: Перезапрос Sitemap (Яндекс)');
    console.log('='.repeat(70) + '\n');
    console.log(`📊 Всего поддоменов: ${links.length}\n`);
    console.log(`🖥️  Размер окна: ${dimensions.width}x${dimensions.height}\n`);

    let success = 0;
    let errors = 0;
    let errorLinks = [];

    for (let i = 0; i < links.length; i++) {
      const subdomain = links[i];
      const sitemapUrl = `https://webmaster.yandex.ru/site/https:${subdomain}:443/indexing/sitemap/`;

      console.log(`${i + 1}/${links.length}: ${subdomain}`);

      try {
        await page.goto(sitemapUrl, { waitUntil: 'networkidle2', timeout: 30000 });
        await delay(1500);

        try {
          const svgSelector = 'button.sitemap-item__recrawl > span > svg';
          const svgElement = await page.$(svgSelector);

          if (svgElement) {
            const parentButton = await page.evaluateHandle(el => el.closest('button'), svgElement);
            await parentButton.click();
            console.log(`   ✅ Кнопка нажата`);
            success++;
          } else {
            const fallbackButtonSelector = '.RecrawlSitemapButton';
            const fallbackButton = await page.$(fallbackButtonSelector);
            if (fallbackButton) {
              await fallbackButton.click();
              console.log(`   ✅ Кнопка нажата (ЗС)`);
              success++;
            } else {
              console.log(`   ❌ Кнопка не найдена`);
              errors++;
              errorLinks.push(subdomain);
            }
          }
        } catch (err) {
          console.log(`   ❌ Ошибка: ${err.message.split('\n')[0]}`);
          errors++;
          errorLinks.push(subdomain);
        }

        await delay(2000);

      } catch (err) {
        console.log(`   ❌ Ошибка загрузки: ${err.message.split('\n')[0]}`);
        errors++;
        errorLinks.push(subdomain);
      }
    }

    await browser.disconnect();

    console.log('\n' + '='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log(`✅ Успешно: ${success}`);
    console.log(`❌ Ошибок: ${errors}`);
    console.log(`📋 Всего: ${links.length}`);

    if (errorLinks.length > 0) {
      console.log('\n🔴 ССЫЛКИ С ОШИБКАМИ:');
      errorLinks.forEach((link, idx) => {
        console.log(`   ${idx + 1}. ${link}`);
      });
    }

    console.log('='.repeat(70));

  } catch (err) {
    console.error('❌ Ошибка подключения к браузеру:', err.message);
  }
})();