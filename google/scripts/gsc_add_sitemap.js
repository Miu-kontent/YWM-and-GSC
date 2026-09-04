// =============================================================================
// СКРИПТ: Добавление Sitemap в Google Search Console
// =============================================================================

const fs = require('fs');
const path = require('path');
const { loadConfig } = require('./loadConfig');
const { loadGoogleConfig } = require('./loadGoogleConfig');

const config = loadConfig('gsc_add_sitemap');
if (!config) process.exit(1);

const googleConfig = loadGoogleConfig();
if (!googleConfig) process.exit(1);

const { gsc_subdomains, gsc_sitemap_path } = config;
const { google } = require('googleapis');

// =============================================================================
// АВТОРИЗАЦИЯ GOOGLE
// =============================================================================

function getAuthClient() {
    const oauth2Client = new google.auth.OAuth2(
        googleConfig.client_id,
        googleConfig.client_secret,
        googleConfig.redirect_uri
    );
    
    oauth2Client.setCredentials({
        access_token: googleConfig.access_token,
    });
    
    return oauth2Client;
}

// =============================================================================
// ДОБАВЛЕНИЕ SITEMAP С RETRY
// =============================================================================

async function addSitemap(siteUrl, sitemapUrl, auth, retryCount = 0) {
    const webmasters = google.webmasters({
        version: "v3",
        auth: auth,
    });
    
    try {
        await webmasters.sitemaps.submit({
            siteUrl: siteUrl,
            feedpath: sitemapUrl,
        });
        console.log(`   ✅ Sitemap добавлен: ${siteUrl}`);
        return { success: true, error: null };
    } catch (err) {
        const errorMsg = err.message.split('\n')[0];
        
        if (errorMsg.includes('ECONNRESET')) {
            console.log(`   ❌ Ошибка - сервер неожиданно вас сбросил - проверьте эту ссылку позже вручную: ${siteUrl}`);
            return { success: false, error: 'Сервер сбросил соединение', url: siteUrl };
        }
        
        const isQuotaError = errorMsg.includes('Quota exceeded') || errorMsg.includes('rate limit');
        
        if (isQuotaError && retryCount < 3) {
            const waitTime = 30000;
            console.log(`   ⏳ Квота превышена, ждём ${waitTime/1000} сек... (попытка ${retryCount + 1}/3)`);
            await new Promise(resolve => setTimeout(resolve, waitTime));
            return addSitemap(siteUrl, sitemapUrl, auth, retryCount + 1);
        }
        
        console.log(`   ❌ Ошибка ${siteUrl}: ${errorMsg}`);
        return { success: false, error: errorMsg, url: siteUrl };
    }
}

// =============================================================================
// ОСНОВНАЯ ФУНКЦИЯ
// =============================================================================

async function main() {
    console.log('='.repeat(70));
    console.log('🚀 ЗАПУСК: Добавление Sitemap в Google Search Console');
    console.log('='.repeat(70));
    console.log();
    
    if (!googleConfig.client_id || !googleConfig.client_secret || !googleConfig.access_token) {
        console.log('❌ Отсутствуют переменные в google/config.json');
        return;
    }
    
    const domains = gsc_subdomains || [];
    const sitemapPath = gsc_sitemap_path || '/sitemap/';
    
    if (!domains || domains.length === 0) {
        console.log('❌ Нет поддоменов для обработки!');
        return;
    }
    
    const auth = getAuthClient();
    
    console.log(`📊 Всего поддоменов: ${domains.length}`);
    console.log(`📁 Путь к Sitemap: ${sitemapPath}`);
    console.log(`⏱️  Задержка между запросами: 3 секунды`);
    console.log();
    
    let success = 0;
    let errors = 0;
    const errorUrls = [];
    
    for (let i = 0; i < domains.length; i++) {
        const domain = domains[i];
        
        const baseUrl = domain.endsWith('/') ? domain : domain + '/';
        const cleanPath = sitemapPath.startsWith('/') ? sitemapPath.slice(1) : sitemapPath;
        const sitemapUrl = baseUrl + cleanPath;
        
        console.log(`${i + 1}/${domains.length}: ${domain}`);
        
        const result = await addSitemap(domain, sitemapUrl, auth);
        if (result.success) {
            success++;
        } else {
            errors++;
            if (result.url) errorUrls.push(result.url);
        }
        
        await new Promise(resolve => setTimeout(resolve, 1500));
    }
    
    console.log();
    console.log('='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log(`✅ Успешно добавлено Sitemap: ${success}`);
    console.log(`❌ Ошибок: ${errors}`);
    console.log(`📋 Всего: ${domains.length}`);
    console.log('='.repeat(70));
    
    console.log();
    console.log('🔴 СПИСОК ССЫЛОК С ОШИБКАМИ:');
    console.log('='.repeat(70));
    if (errorUrls.length > 0) {
        errorUrls.forEach(url => console.log(`"${url}",`));
    } else {
        console.log('Нет ошибок');
    }
    console.log('='.repeat(70));
}

main().catch(error => {
    console.log('❌ КРИТИЧЕСКАЯ ОШИБКА:', error.message);
});