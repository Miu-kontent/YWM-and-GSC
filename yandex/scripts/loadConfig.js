const fs = require('fs');
const path = require('path');

function loadConfig(scriptName) {
    const configPath = path.join(__dirname, '..', 'arrays', `${scriptName}.json`);
    try {
        if (fs.existsSync(configPath)) {
            return JSON.parse(fs.readFileSync(configPath, 'utf-8'));
        }
    } catch (e) {
        console.log(`⚠️ Не удалось загрузить ${configPath}: ${e.message}`);
        return null;
    }

    console.log(`❌ Файл конфигурации не найден: ${configPath}`);
    return null;
}

module.exports = { loadConfig };