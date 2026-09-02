const fs = require('fs');
const path = require('path');

function loadConfig(scriptName) {
    const configPath = path.join(__dirname, '..', `array_${scriptName}.js`);
    try {
        if (fs.existsSync(configPath)) {
            delete require.cache[require.resolve(configPath)];
            return require(configPath);
        }
    } catch (e) {
        console.log(`⚠️ Не удалось загрузить ${configPath}: ${e.message}`);
    }
    
    const fallbackPaths = [
        path.join(__dirname, '..', 'arr.js'),
        path.join(__dirname, 'arr.js'),
    ];
    
    for (const p of fallbackPaths) {
        try {
            if (fs.existsSync(p)) {
                delete require.cache[require.resolve(p)];
                return require(p);
            }
        } catch (e) {}
    }
    
    console.log('❌ Файл конфигурации не найден!');
    return null;
}

module.exports = { loadConfig };