const fs = require('fs');
const path = require('path');

function loadGoogleConfig() {
    const configPath = path.join(__dirname, '..', 'config.json');
    try {
        if (fs.existsSync(configPath)) {
            delete require.cache[require.resolve(configPath)];
            return require(configPath);
        }
    } catch (e) {
        console.log(`⚠️ Не удалось загрузить ${configPath}: ${e.message}`);
    }
    console.log('❌ Файл google/config.json не найден!');
    return null;
}

module.exports = { loadGoogleConfig };