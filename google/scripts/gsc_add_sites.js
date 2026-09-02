
// СКРИПТ: Добавление поддоменов в Google Search Console
const fs = require('fs');
const path = require('path');
const { loadConfig } = require('./loadConfig');
const config = loadConfig('gsc_add_sites');
if (!config) process.exit(1);

const { gsc_subdomains } = config;
const { google } = require('googleapis');

// ФУНКЦИЯ ДЛЯ ПОНЯТНОГО ОБЪЯСНЕНИЯ ОШИБОК
function explainError(errorMsg, siteUrl) {
    // Лимит сайтов в аккаунте Google
    if (errorMsg.includes('Cannot add any more sites')) {
        return {
            short: `⚠️ ${siteUrl}: Достигнут лимит сайтов в Google Search Console`,
            solution: `🔧 РЕШЕНИЕ: Удалите неиспользуемые сайты из Search Console или используйте другой аккаунт Google`
        };
    }
    
    // Неверные учетные данные (токен)
    if (errorMsg.includes('invalid authentication credentials') || errorMsg.includes('OAuth 2 access token')) {
        return {
            short: `❌ ${siteUrl}: Проблема с токеном доступа`,
            solution: `🔧 РЕШЕНИЕ: Получите новый ACCESS_TOKEN в .env (файл в папке Массивы)`
        };
    }
    
    // Превышение квоты
    if (errorMsg.includes('Quota exceeded') || errorMsg.includes('rate limit')) {
        return {
            short: `⏳ ${siteUrl}: Превышен лимит запросов`,
            solution: `🔧 РЕШЕНИЕ: Подождите 1-2 минуты, скрипт автоматически повторит попытку`
        };
    }
    
    // Сайт уже добавлен
    if (errorMsg.includes('already exists') || errorMsg.includes('duplicate')) {
        return {
            short: `ℹ️ ${siteUrl}: Уже добавлен ранее`,
            solution: null
        };
    }
    
    // Неверный формат URL
    if (errorMsg.includes('Invalid site') || errorMsg.includes('URL')) {
        return {
            short: `⚠️ ${siteUrl}: Неверный формат адреса`,
            solution: `🔧 РЕШЕНИЕ: Убедитесь, что URL начинается с https:// и не имеет слеша в конце`
        };
    }
    
    // Нет доступа
    if (errorMsg.includes('Permission denied') || errorMsg.includes('forbidden')) {
        return {
            short: `⛔ ${siteUrl}: Нет прав на добавление`,
            solution: `🔧 РЕШЕНИЕ: Проверьте, что ваш аккаунт Google имеет доступ к Search Console`
        };
    }
    
    // Общая ошибка
    return {
        short: `❌ ${siteUrl}: ${errorMsg.substring(0, 80)}`,
        solution: `🔧 РЕШЕНИЕ: Проверьте подключение к интернету и правильность данных в .env`
    };
}

// ЧТЕНИЕ .env ФАЙЛА - теперь .env генерируется в google/.env
function loadEnvFromArrays() {
    try {
        const envPath = path.join(__dirname, '..', '.env');
        if (!fs.existsSync(envPath)) {
            console.log('❌ Файл .env не найден!');
            return false;
        }
        
        console.log(`✅ Найден файл .env: ${envPath}`);
        
        const envContent = fs.readFileSync(envPath, 'utf8');
        const envLines = envContent.split('\n');
        
        for (const line of envLines) {
            const trimmed = line.trim();
            if (trimmed && !trimmed.startsWith('#')) {
                const [key, value] = trimmed.split('=');
                if (key && value) {
                    process.env[key] = value;
                }
            }
        }
        
        return true;
    } catch (error) {
        console.log(`❌ Ошибка чтения .env: ${error.message}`);
        return false;
    }
}

// АВТОРИЗАЦИЯ GOOGLE
function getAuthClient() {
    const oauth2Client = new google.auth.OAuth2(
        process.env.CLIENT_ID,
        process.env.CLIENT_SECRET,
        process.env.REDIRECT_URI
    );
    
    oauth2Client.setCredentials({
        access_token: process.env.ACCESS_TOKEN,
    });
    
    return oauth2Client;
}

// ДОБАВЛЕНИЕ САЙТА С RETRY
async function addSite(siteUrl, auth, retryCount = 0) {
    const webmasters = google.webmasters({
        version: "v3",
        auth: auth,
    });
    
    try {
        await webmasters.sites.add({
            siteUrl: siteUrl,
        });
        console.log(`   ✅ ДОБАВЛЕН: ${siteUrl}`);
        return { success: true, error: null };
    } catch (err) {
        const errorMsg = err.message.split('\n')[0];
        const isQuotaError = errorMsg.includes('Quota exceeded') || errorMsg.includes('rate limit');
        
        if (isQuotaError && retryCount < 3) {
            const waitTime = 30000;
            console.log(`   ⏳ Лимит запросов, ждём ${waitTime/1000} сек... (попытка ${retryCount + 1}/3)`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
            return addSite(siteUrl, auth, retryCount + 1);
        }
        
        // Получаем понятное объяснение ошибки
        const explanation = explainError(errorMsg, siteUrl);
        console.log(`   ${explanation.short}`);
        if (explanation.solution) {
            console.log(`   ${explanation.solution}`);
        }
        
        return { success: false, error: errorMsg, url: siteUrl };
    }
}

// ОСНОВНАЯ ФУНКЦИЯ
async function main() {
    console.log('='.repeat(70));
    console.log('🚀 ДОБАВЛЕНИЕ ПОДДОМЕНОВ В GOOGLE SEARCH CONSOLE');
    console.log('='.repeat(70));
    console.log();
    
    if (!loadEnvFromArrays()) {
        return;
    }
    
    if (!process.env.CLIENT_ID || !process.env.CLIENT_SECRET || !process.env.ACCESS_TOKEN) {
        console.log('❌ ОТСУТСТВУЮТ ДАННЫЕ В .env');
        console.log('   Добавьте: CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN');
        return;
    }
    
    const subdomains = gsc_subdomains || [];
    
    if (!subdomains || subdomains.length === 0) {
        console.log('❌ НЕТ ПОДДОМЕНОВ ДЛЯ ОБРАБОТКИ!');
        return;
    }
    
    const auth = getAuthClient();
    
    console.log(`📊 ВСЕГО: ${subdomains.length} поддоменов`);
    console.log(`⏱️  ЗАДЕРЖКА: 3 секунды между запросами`);
    console.log();
    
    let success = 0;
    let errors = 0;
    const errorUrls = [];
    
    for (let i = 0; i < subdomains.length; i++) {
        const subdomain = subdomains[i];
        console.log(`${i + 1}/${subdomains.length}: ${subdomain}`);
        
        const result = await addSite(subdomain, auth);
        if (result.success) {
            success++;
        } else {
            errors++;
            if (result.url) errorUrls.push(result.url);
        }
        
        await new Promise(resolve => setTimeout(resolve, 3000));
    }
    
    // ИТОГИ
    console.log();
    console.log('='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log(`   ✅ УСПЕШНО: ${success}`);
    console.log(`   ❌ ОШИБОК: ${errors}`);
    console.log(`   📋 ВСЕГО: ${subdomains.length}`);
    
    // СПИСОК ОШИБОК (только если есть)
    if (errorUrls.length > 0) {
        console.log();
        console.log('='.repeat(70));
        console.log('🔴 СПИСОК САЙТОВ С ОШИБКАМИ:');
        console.log('='.repeat(70));
        errorUrls.forEach(url => console.log(`   ${url}`));
        console.log();
        console.log('💡 КАК ИСПРАВИТЬ:');
        console.log('   • Достигнут лимит сайтов → удалите неиспользуемые сайты из Search Console');
        console.log('   • Ошибка с токеном → получите новый ACCESS_TOKEN');
        console.log('   • Ошибка с правами → проверьте аккаунт Google');
        console.log('   • Сайт уже добавлен → ничего делать не нужно');
    }
    
    console.log('='.repeat(70));
}

main().catch(error => {
    console.log('❌ КРИТИЧЕСКАЯ ОШИБКА:', error.message);
});