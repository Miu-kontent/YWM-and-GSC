// =============================================================================
// Подтверждение прав (верификация) сайтов в Google Search Console
// =============================================================================

const fs = require('fs');
const path = require('path');
const { loadConfig } = require('./loadConfig');
const { loadGoogleConfig } = require('./loadGoogleConfig');

const config = loadConfig('gsc_verify');
if (!config) process.exit(1);

const googleConfig = loadGoogleConfig();
if (!googleConfig) process.exit(1);

const { gsc_subdomains } = config;
const { google } = require('googleapis');
const https = require('https');
const url = require('url');


// =============================================================================
// 2. ЗАГРУЗКА ПОДДОМЕНОВ ИЗ arr.js
// =============================================================================

function getSubdomainsFromArrJS() {
    const arrPaths = [
        path.join(__dirname, '..', 'Скрипты', 'arr.js'),
        path.join(__dirname, 'Скрипты', 'arr.js'),
        'Массивы/arr.js',
        path.join(process.cwd(), 'Скрипты', 'arr.js')
    ];

    let arrPath = null;
    for (const p of arrPaths) {
        if (fs.existsSync(p)) {
            arrPath = p;
            break;
        }
    }

    if (!arrPath) {
        console.log('❌ Файл arr.js не найден!');
        return [];
    }

    delete require.cache[require.resolve(arrPath)];
    const config = require(arrPath);

    if (config.gsc_subdomains && Array.isArray(config.gsc_subdomains)) {
        console.log(`✅ Загружено ${config.gsc_subdomains.length} поддоменов`);
        return config.gsc_subdomains;
    }

    console.log('❌ Массив gsc_subdomains не найден в module.exports');
    return [];
}


// =============================================================================
// 3. ПОЛУЧЕНИЕ ACCESS TOKEN
// =============================================================================

const scopes = ['https://www.googleapis.com/auth/siteverification'];

async function getAccessToken(oauth2Client) {
    let authCode = googleConfig.auth_code;
    if (authCode && authCode.includes('%')) {
        try {
            authCode = decodeURIComponent(authCode);
            console.log('🔓 AUTH_CODE автоматически декодирован');
        } catch(e) {
            console.log('⚠️ Не удалось декодировать');
        }
    }

    if (!authCode || authCode.trim() === '') {
        const authUrl = oauth2Client.generateAuthUrl({
            access_type: 'offline',
            scope: scopes,
        });
        console.log('\n🔗 Перейдите по ссылке и получите код:');
        console.log(authUrl);
        console.log('\n📌 Вставьте полученный код в google/config.json как auth_code=ваш_код');
        return false;
    }

    try {
        const { tokens } = await oauth2Client.getToken(authCode);
        oauth2Client.setCredentials(tokens);
        console.log('✅ Токен получен');
        
        // Обновляем access_token в config.json
        googleConfig.access_token = tokens.access_token;
        if (tokens.refresh_token) {
            googleConfig.refresh_token = tokens.refresh_token;
        }
        googleConfig.auth_code = '';
        
        const configPath = path.join(__dirname, '..', 'config.json');
        fs.writeFileSync(configPath, JSON.stringify(googleConfig, null, 2));
        console.log('✅ Токены сохранены в google/config.json, auth_code очищен');
        return true;
    } catch (err) {
        console.error('❌ Ошибка получения токена:', err.message);
        return false;
    }
}


// =============================================================================
// 4. ПОЛУЧЕНИЕ СПИСКА ВЕРИФИЦИРОВАННЫХ САЙТОВ
// =============================================================================

async function getVerifiedSites(oauth2Client) {
    const siteVerification = google.siteVerification({ version: 'v1', auth: oauth2Client });
    const verifiedList = new Set();
    let pageToken = null;

    try {
        do {
            const res = await siteVerification.webResource.list({
                maxResults: 100,
                pageToken: pageToken,
            });
            if (res.data.items) {
                for (const item of res.data.items) {
                    if (item.site && item.site.identifier) {
                        verifiedList.add(item.site.identifier);
                    }
                }
            }
            pageToken = res.data.nextPageToken;
        } while (pageToken);
    } catch (err) {
        console.error('❌ Ошибка при получении списка верифицированных сайтов:', err.message);
    }
    return verifiedList;
}


// =============================================================================
// 5. ПРОВЕРКА НАЛИЧИЯ ANALYTICS КОДА НА САЙТЕ
// =============================================================================

async function checkAnalyticsCode(siteUrl) {
    try {
        return new Promise((resolve) => {
            const parsedUrl = new URL(siteUrl);
            const options = {
                hostname: parsedUrl.hostname,
                path: parsedUrl.pathname || '/',
                method: 'GET',
                timeout: 5000,
                headers: { 
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
            };
            
            const req = https.request(options, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    // Проверяем наличие кода Google Analytics
                    const hasAnalytics = data.includes('gtag.js') || 
                                        data.includes('G-') || 
                                        data.includes('google-analytics') ||
                                        data.includes('analytics.js') ||
                                        data.includes('gtm.js');
                    resolve(hasAnalytics);
                });
            });
            
            req.on('error', () => resolve(false));
            req.on('timeout', () => {
                req.destroy();
                resolve(false);
            });
            req.end();
        });
    } catch (e) {
        return false;
    }
}


// =============================================================================
// 6. ВЕРИФИКАЦИЯ С АВТОМАТИЧЕСКИМ ВЫБОРОМ МЕТОДА
// =============================================================================

async function verifySite(siteUrl, oauth2Client, isAlreadyVerifiedForMe) {
    if (isAlreadyVerifiedForMe) {
        console.log(`   ✅ Уже верифицирован для этого аккаунта. Пропускаем.`);
        return true;
    }

    const siteVerification = google.siteVerification({ version: 'v1', auth: oauth2Client });
    
    // Проверяем наличие Analytics кода на сайте
    console.log(`   🔍 Проверяю наличие Analytics кода...`);
    const hasAnalytics = await checkAnalyticsCode(siteUrl);
    
    // Формируем список методов в приоритетном порядке
    let methods = ['META', 'FILE'];
    if (hasAnalytics) {
        methods.unshift('ANALYTICS');
        console.log(`   📊 Найден код Analytics на сайте`);
    } else {
        console.log(`   ℹ️ Код Analytics не найден, использую META/FILE`);
    }

    // Перебираем методы
    for (const method of methods) {
        try {
            console.log(`   🔄 Пробую метод: ${method}`);
            await siteVerification.webResource.insert({
                verificationMethod: method,
                resource: { site: { identifier: siteUrl, type: 'SITE' } },
            });
            console.log(`   ✅ Верифицирован: ${siteUrl} (способ: ${method})`);
            return true;
        } catch (err) {
            if (err.message.includes('already exists')) {
                console.log(`   ℹ️ Уже верифицирован (возможно, другим способом или аккаунтом): ${siteUrl}`);
                return true;
            }
            if (err.message.includes('insufficient') || err.message.includes('forbidden') || err.message.includes('403')) {
                console.log(`   ⚠️ Недостаточно прав для подтверждения ${siteUrl}. Пропускаем.`);
                return true;
            }
            // Если метод не подошел - пробуем следующий
            console.log(`   ⚠️ Метод ${method} не подошел, пробую следующий...`);
        }
    }
    
    console.log(`   ❌ Ошибка: ${siteUrl} - ни один метод не подошел`);
    console.log(`   📖 Не найден код подтверждения.`);
    return false;
}


// =============================================================================
// 7. ОСНОВНАЯ ФУНКЦИЯ
// =============================================================================

async function main() {
    console.log('='.repeat(70));
    console.log('🚀 ВЕРИФИКАЦИЯ В GOOGLE SEARCH CONSOLE');
    console.log('='.repeat(70) + '\n');

    if (!googleConfig.client_id || !googleConfig.client_secret || !googleConfig.redirect_uri) {
        console.log('❌ Отсутствуют данные в google/config.json');
        console.log('   Добавьте: client_id, client_secret, redirect_uri');
        return;
    }

    const subdomains = gsc_subdomains || [];
    if (subdomains.length === 0) {
        console.log('❌ Нет поддоменов для обработки!');
        return;
    }

    const oauth2Client = new google.auth.OAuth2(
        googleConfig.client_id,
        googleConfig.client_secret,
        googleConfig.redirect_uri
    );

    // Если есть access_token, используем его
    if (googleConfig.access_token) {
        oauth2Client.setCredentials({
            access_token: googleConfig.access_token,
            refresh_token: googleConfig.refresh_token
        });
    }

    const hasToken = await getAccessToken(oauth2Client);
    if (!hasToken) return;

    // Получаем список уже верифицированных сайтов
    console.log('📡 Получаю список уже верифицированных сайтов...');
    const verifiedSites = await getVerifiedSites(oauth2Client);
    console.log(`✅ Найдено верифицированных сайтов: ${verifiedSites.size}\n`);

    console.log(`📊 Всего поддоменов для проверки: ${subdomains.length}\n`);

    let success = 0;
    let errors = 0;

    for (let i = 0; i < subdomains.length; i++) {
        const site = subdomains[i];
        const isAlreadyVerified = verifiedSites.has(site);
        console.log(`\n${i + 1}/${subdomains.length}: ${site}`);
        
        const result = await verifySite(site, oauth2Client, isAlreadyVerified);
        
        if (result === true) {
            success++;
        } else {
            errors++;
        }
    }

    console.log('\n' + '='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log(`✅ Успешно обработано (верифицированы или пропущены): ${success}`);
    console.log(`❌ Ошибок: ${errors}`);
    console.log(`📋 Всего: ${subdomains.length}`);
    console.log('='.repeat(70));
}

main().catch(err => {
    console.error('❌ КРИТИЧЕСКАЯ ОШИБКА:', err.message);
});