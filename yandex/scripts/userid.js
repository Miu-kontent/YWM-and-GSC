// =============================================================================
// СКРИПТ ДЛЯ ПОЛУЧЕНИЯ USER_ID ИЗ ЯНДЕКС API
// Принимает oauth_token как аргумент командной строки
// =============================================================================

// Берём oauth_token из аргумента командной строки
const oauthToken = process.argv[2];

if (!oauthToken) {
    console.log('❌ Не передан oauth_token');
    console.log('Использование: node userid.js "ваш_oauth_token"');
    process.exit(1);
}

async function getUserId() {
    try {
        const response = await fetch('https://api.webmaster.yandex.net/v4/user/', {
            method: 'GET',
            headers: {
                'Authorization': `OAuth ${oauthToken}`,
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            console.log(`❌ Ошибка API: ${response.status}`);
            process.exit(1);
        }
        
        const data = await response.json();
        const userId = data.user_id || data.uid;
        
        if (userId) {
            console.log(userId);
        } else {
            console.log('❌ user_id не найден');
            process.exit(1);
        }
        
    } catch (error) {
        console.log(`❌ Ошибка: ${error.message}`);
        process.exit(1);
    }
}

getUserId();