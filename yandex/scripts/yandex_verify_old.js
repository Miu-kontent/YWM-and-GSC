
// СКРИПТ: УМНОЕ ПОДТВЕРЖДЕНИЕ ПРАВ В ЯНДЕКС ВЕБМАСТЕРЕ

const { loadConfig } = require('./loadConfig');

function loadYandexSettings() {
    const config = loadConfig('yandex_verify');
    if (!config) return null;
    
    if (!config.yandexSettings) {
        console.log('❌ В конфиге нет yandexSettings');
        return null;
    }
    
    const oauthToken = config.yandexSettings.oauth_token;
    const userId = config.yandexSettings.user_id;
    const subdomains = config.links || [];
    
    if (!oauthToken || !userId) {
        console.log('❌ В yandexSettings нет oauth_token или user_id');
        return null;
    }
    
    if (subdomains.length === 0) {
        console.log('❌ Нет поддоменов в массиве links');
        return null;
    }
    
    console.log(`✅ Загружено ${subdomains.length} поддоменов`);
    
    return { oauthToken, userId, subdomains };
}

// ФУНКЦИЯ ДЛЯ ПОНЯТНОГО ОБЪЯСНЕНИЯ ОШИБОК

function explainError(responseStatus, errorText, subdomain, method) {
    if (responseStatus === 401) {
        return `   📖 Неверный OAuth-токен\n   🔧 Решение: Обновите oauth_token в arr.js`;
    }
    if (responseStatus === 403) {
        return `   📖 Нет доступа к сайту\n   🔧 Решение: Добавьте сайт в Яндекс Вебмастер вручную`;
    }
    if (responseStatus === 404) {
        return `   📖 Сайт не найден в Яндекс Вебмастере\n   🔧 Решение: Сначала добавьте сайт через веб-интерфейс`;
    }
    if (responseStatus === 429) {
        return `   ⏳ Превышен лимит запросов\n   🔧 Решение: Подождите 1-2 минуты`;
    }
    if (errorText && errorText.includes('verification')) {
        return `   📖 Проблема с подтверждением методом ${method}\n   🔧 Решение: Проверьте, что на сайте добавлен код подтверждения`;
    }
    return `   📖 ${responseStatus} - ${errorText ? errorText.substring(0, 100) : 'неизвестная ошибка'}`;
}

// ПРОВЕРКА ОДНИМ МЕТОДОМ

async function verifyWithMethod(hostId, userId, oauthToken, method) {
    const verificationUrl = `https://api.webmaster.yandex.net/v4/user/${userId}/hosts/${hostId}/verification?verification_type=${method}`;
    
    try {
        const response = await fetch(verificationUrl, {
            method: 'POST',
            headers: {
                'Authorization': `OAuth ${oauthToken}`,
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            return { success: true, status: response.status, method };
        }
        
        const errorText = await response.text();
        return { success: false, status: response.status, error: errorText, method };
        
    } catch (error) {
        return { success: false, status: 0, error: error.message, method };
    }
}

// УМНАЯ ВЕРИФИКАЦИЯ — ПЕРЕБОР МЕТОДОВ

async function verifySmart(subdomain, userId, oauthToken) {
    // Формируем host_id
    let hostId = subdomain;
    if (!hostId.includes('https:')) {
        hostId = `https:${hostId}:443`;
    }
    
    // Сначала пробуем META_TAG
    console.log(`   🔍 Пробуем META_TAG...`);
    const metaResult = await verifyWithMethod(hostId, userId, oauthToken, 'META_TAG');
    
    if (metaResult.success) {
        console.log(`   ✅ Подтверждено через META_TAG`);
        return { success: true, method: 'META_TAG', status: metaResult.status };
    }
    
    // Если META_TAG не сработал (кроме случая "уже подтверждено")
    if (metaResult.status === 409) {
        console.log(`   ℹ️ Уже подтверждено ранее (META_TAG)`);
        return { success: true, method: 'META_TAG (уже было)', status: 409 };
    }
    
    // Пробуем HTML_FILE
    console.log(`   🔍 META_TAG не сработал, пробуем HTML_FILE...`);
    const fileResult = await verifyWithMethod(hostId, userId, oauthToken, 'HTML_FILE');
    
    if (fileResult.success) {
        console.log(`   ✅ Подтверждено через HTML_FILE`);
        return { success: true, method: 'HTML_FILE', status: fileResult.status };
    }
    
    if (fileResult.status === 409) {
        console.log(`   ℹ️ Уже подтверждено ранее (HTML_FILE)`);
        return { success: true, method: 'HTML_FILE (уже было)', status: 409 };
    }
    
    // Оба метода не сработали — выдаём понятную ошибку
    console.log(`   ❌ Ошибка: ни один метод не сработал`);
    
    // Показываем подробности первой ошибки (META_TAG)
    if (!metaResult.success && metaResult.status !== 409) {
        const explanation = explainError(metaResult.status, metaResult.error, subdomain, 'META_TAG');
        console.log(`   ${explanation}`);
    }
    
    return { success: false, error: metaResult.error || fileResult.error };
}

// ОСНОВНАЯ ФУНКЦИЯ
async function main() {
    console.log('='.repeat(70));
    console.log('🚀 УМНОЕ ПОДТВЕРЖДЕНИЕ ПРАВ В ЯНДЕКС ВЕБМАСТЕРЕ');
    console.log('   (сначала META_TAG, если не получится — HTML_FILE)');
    console.log('='.repeat(70));
    console.log();
    
    const settings = loadYandexSettings();
    if (!settings) {
        console.log('❌ Не удалось загрузить настройки из arr.js');
        return;
    }
    
    const { oauthToken, userId, subdomains } = settings;
    
    console.log(`📊 Всего поддоменов: ${subdomains.length}`);
    console.log(`🆔 User ID: ${userId}`);
    console.log(`🔑 OAuth Token: ${oauthToken.substring(0, 20)}...`);
    console.log();
    console.log('🔄 Начинаем умную верификацию (автоперебор методов)...');
    console.log();
    
    let success = 0;
    let already = 0;
    let errors = 0;
    const errorList = [];
    
    for (let i = 0; i < subdomains.length; i++) {
        const subdomain = subdomains[i];
        console.log(`${i + 1}/${subdomains.length}: ${subdomain}`);
        
        const result = await verifySmart(subdomain, userId, oauthToken);
        
        if (result.success) {
            if (result.status === 409 || result.method.includes('уже')) {
                already++;
            } else {
                success++;
            }
        } else {
            errors++;
            errorList.push({ url: subdomain, error: result.error });
        }
        
        // Задержка между запросами
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    // ИТОГИ
    console.log();
    console.log('='.repeat(70));
    console.log('📊 ИТОГИ:');
    console.log(`   ✅ НОВЫХ подтверждений: ${success}`);
    console.log(`   ℹ️ УЖЕ были подтверждены: ${already}`);
    console.log(`   ❌ ОШИБОК: ${errors}`);
    console.log(`   📋 ВСЕГО: ${subdomains.length}`);
    
    if (errorList.length > 0) {
        console.log();
        console.log('='.repeat(70));
        console.log('🔴 СПИСОК САЙТОВ С ОШИБКАМИ:');
        console.log('='.repeat(70));
        errorList.forEach((item, idx) => {
            console.log(`${idx + 1}. ${item.url}`);
        });
        console.log();
        console.log('💡 КАК ИСПРАВИТЬ:');
        console.log('   • 401 → Обновите oauth_token в arr.js');
        console.log('   • 403 → Добавьте сайт в Яндекс Вебмастер вручную');
        console.log('   • 404 → Проверьте правильность URL');
        console.log('   • Если кнопки не сработали → добавьте META-тег или HTML-файл на сайт');
    }
    
    console.log('='.repeat(70));
}

main().catch(error => {
    console.log('❌ КРИТИЧЕСКАЯ ОШИБКА:', error.message);
});