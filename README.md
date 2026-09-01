# YWM-and-GSC — Яндекс Вебмастер и Google Search Console

Автоматизация рутинных задач в **Яндекс.Вебмастере** и **Google Search Console** через Puppeteer и Google API.

> 🇷🇺 **Язык проекта:** русский. Коммиты, документация и диалоги — на русском.

---

## 📦 Что внутри

### 🎯 Основные возможности

| Категория | Скрипты | Описание |
|-----------|---------|----------|
| **Яндекс — Подтверждение прав** | `yandex_verify.js` | Умная верификация: пробует META_TAG, потом HTML_FILE. Авто-ретраи, понятные ошибки (401/403/404/429). |
| **Яндекс — Регионы** | `addRegions.js` | Массовое добавление регионов поддоменам. Берёт город из `city[]`, контакт из `contactPath`. |
| **Яндекс — Метрика** | `metrika_bind.js` | Привязка поддоменов к счётчику Яндекс.Метрики. Ищет фреймы, скроллит, кликает «Привязать к Вебмастеру». |
| **Яндекс — Обход по счётчикам** | `addMetrics.js` | Включает «Обход по счётчикам» в настройках индексирования. |
| **Яндекс — Sitemap** | `sitemap.py` | Добавление sitemap через Яндекс API (OAuth). |
| **Яндекс — Переобход** | `reindex.js`, `recrawl.js` | Переобход страниц / перезапрос sitemap. |
| **Яндекс — Проверки** | `Regi.js`, `metriks.js`, `recomen.js`, `errors.js` | Проверка региона, обхода счётчиков, рекомендаций, ошибок. |
| **Яндекс — Удаление** | `yandex_sites_to_delete.js` | Удаление поддоменов из Яндекс.Вебмастера. |
| **Google — Добавление сайтов** | `gsc_add_sites.js` | Массовое добавление поддоменов в GSC через Google API (OAuth2). Ретраи при квоте. |
| **Google — Верификация** | `gsc_verify.js` | Умная верификация: ANALYTICS → META → FILE. Проверяет наличие GA кода на сайте. Авто-очистка AUTH_CODE. |
| **Google — Sitemap** | `gsc_add_sitemap.js` | Добавление sitemap в GSC. |
| **Google — Удаление** | `gsc_delete_sites.js`, `gsc_delete_unverified.js` | Удаление сайтов / удаление **неподтверждённых** сайтов из GSC (через Puppeteer в UI). |
| **Утилиты** | `userid.js` | Получение `user_id` по OAuth-токену для Яндекс API. |

---

## 🏗 Архитектура

```
YWM-and-GSC/
├── launcher.py          # GUI-лаунчер (CustomTkinter) — запуск браузеров и скриптов
├── data_editor.py       # Окно редактирования данных (arr.js + .env) с вкладками
├── package.json         # Зависимости: googleapis, puppeteer
├── requirements.txt     # Python-зависимости (для sitemap.py)
├── scripts/             # JavaScript/Python скрипты (копируются из dist/Скрипты)
├── arrays/              # Данные: arr.js (поддомены, города, токены) + .env (Google OAuth)
├── dist/                # Скомпилированные .exe (PyInstaller)
└── build/               # Временные файлы сборки
```

### 🔐 Хранение данных

| Файл | Назначение | Пример содержимого |
|------|------------|-------------------|
| `scripts/arr.js` | **Яндекс + общие данные** — поддомены (`links`), города (`city`), `metricCounterId`, `yandexSettings` (oauth_token, user_id, sitemap_name), `yandex_sites_to_delete`, `gsc_subdomains`, `gsc_sitemap_path`, `gsc_sites_to_delete` | `const links = ["sub.domain.ru"];` |
| `arrays/.env` | **Google OAuth** — `CLIENT_ID`, `CLIENT_SECRET`, `ACCESS_TOKEN`, `REDIRECT_URI`, `AUTH_CODE` (одноразовый) | `CLIENT_ID=xxx.apps.googleusercontent.com` |

> ⚠️ **Важно:** `arr.js` и `.env` **не коммитятся** в git (добавьте в `.gitignore`). Хранятся локально.

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Node.js скрипты
npm install

# Python (для sitemap.py)
pip install -r requirements.txt
```

### 2. Подготовка данных

Создайте папки и файлы:

```
YWM-and-GSC/
├── scripts/
│   └── arr.js          # ← скопируйте из старого проекта или создайте по шаблону
└── arrays/
    └── .env            # ← создайте из шаблона ниже
```

**Шаблон `scripts/arr.js`:**
```javascript
const contactPath = "contacts";

const links = [
    "sub1.domain.ru",
    "sub2.domain.ru"
];

const city = [
    "Москва",
    "Санкт-Петербург"
];

const metricCounterId = "12345678";

const yandexSettings = {
    oauth_token: "y0_AgAAA...",
    user_id: "123456789",
    sitemap_name: "/sitemap.xml"
};

const yandex_sites_to_delete = [
    "https://old-sub.domain.ru/"
];

const gsc_subdomains = [
    "https://sub1.domain.ru/",
    "https://sub2.domain.ru/"
];

const gsc_sitemap_path = "/sitemap.xml";

const gsc_sites_to_delete = [
    "https://old-sub.domain.ru/"
];

const turboPages = [];

module.exports = { 
    links, city, contactPath, turboPages, yandexSettings,
    yandex_sites_to_delete, gsc_subdomains, gsc_sitemap_path,
    gsc_sites_to_delete, metricCounterId 
};
```

**Шаблон `arrays/.env`:**
```env
CLIENT_ID=xxx.apps.googleusercontent.com
CLIENT_SECRET=GOCSPX-xxx
ACCESS_TOKEN=ya29.a0A...
REDIRECT_URI=http://localhost:3000/
AUTH_CODE=4/0A...   # одноразовый, очищается после использования
```

### 3. Запуск браузеров (обязательно перед скриптами)

Запустите лаунчер:
```bash
python launcher.py
```

И нажмите:
1. **🌏 Яндекс (порт 9229)** — откроется Chrome с профилем для Яндекса. Авторизуйтесь в Вебмастере и Метрике. **Не закрывайте окно.**
2. **🔍 Google (порт 9227)** — откроется Chrome с профилем для Google. Авторизуйтесь в Search Console. **Не закрывайте окно.**

### 4. Запуск скриптов

Через лаунчер (GUI) — просто нажмите на нужный скрипт.

Или вручную:
```bash
# Яндекс скрипты (порт 9229)
node scripts/yandex_verify.js
node scripts/addRegions.js
node scripts/metrika_bind.js
# ...

# Google API скрипты (требуют .env)
node scripts/gsc_add_sites.js
node scripts/gsc_verify.js
node scripts/gsc_add_sitemap.js

# Google UI скрипты (порт 9227, Puppeteer)
node scripts/gsc_delete_sites.js
node scripts/gsc_delete_unverified.js

# Python
python scripts/sitemap.py
```

---

## 🖥 Лаунчер (GUI)

`launcher.py` — главное окно управления:
- Запуск браузеров с правильными портами и профилями
- Кнопка **«✏️ Внести свои данные»** — открывает `data_editor.py`
- Список всех скриптов с цветовой индикацией:
  - 🟨 **Жёлтые** — Яндекс
  - 🔴 **Красные** — Google
  - 🐍 **Python** — значок змейки
- Кнопка **«🔄 ОБНОВИТЬ ВСЁ»** — пересканирует папки
- Каждый скрипт запускается в **отдельном окне** с выводом логов (копировать/сохранить/очистить)

`data_editor.py` — редактор данных с вкладками:
- **Яндекс** — links, city, metricCounterId, contactPath, yandexSettings, yandex_sites_to_delete
- **Google** — gsc_subdomains, gsc_sitemap_path, gsc_sites_to_delete
- **Google API** — CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN, REDIRECT_URI, AUTH_CODE
- Кнопки **«💾 Сохранить Яндекс»** и **«💾 Сохранить Google»** — сохраняют раздельно, не затирая чужие данные
- Кнопка **«🔄 Получить user_id»** — запускает `userid.js` с токеном из поля ввода

---

## 📋 Список скриптов (детально)

### Яндекс (Puppeteer, порт 9229)

| Скрипт | Входные данные | Что делает |
|--------|----------------|------------|
| `yandex_verify.js` | `arr.js` → `links`, `yandexSettings` | Верификация сайтов: META_TAG → HTML_FILE. Отчёт: новые / уже было / ошибки. |
| `addRegions.js` | `arr.js` → `links`, `city`, `contactPath` | Для каждого поддомена добавляет регион в Вебмастере. |
| `metrika_bind.js` | `arr.js` → `metricCounterId` | Привязывает все доступные поддомены к счётчику Метрики. |
| `addMetrics.js` | `arr.js` → `links`, `yandexSettings` | Включает «Обход по счётчикам» в настройках индексирования. |
| `sitemap.py` | `arr.js` → `links`, `yandexSettings` | Добавляет sitemap через Яндекс API (OAuth). |
| `reindex.js` | `arr.js` → `links` | Запускает переобход страниц. |
| `recrawl.js` | `arr.js` → `links`, `yandexSettings` | Перезапрашивает sitemap. |
| `Regi.js` | `arr.js` → `links` | Проверяет установленный регион. |
| `metriks.js` | `arr.js` → `links`, `metricCounterId` | Проверяет, включён ли обход по счётчикам. |
| `recomen.js` | `arr.js` → `links` | Проверяет рекомендации Вебмастера. |
| `errors.js` | `arr.js` → `links` | Проверяет ошибки индексирования. |
| `yandex_sites_to_delete.js` | `arr.js` → `yandex_sites_to_delete` | Удаляет указанные сайты из Вебмастера. |
| `userid.js` | `arr.js` → `yandexSettings.oauth_token` | Получает `user_id` по токену (для заполнения `arr.js`). |

### Google API (требуют `.env`)

| Скрипт | Входные данные | Что делает |
|--------|----------------|------------|
| `gsc_add_sites.js` | `.env` + `arr.js` → `gsc_subdomains` | Массовое добавление сайтов в GSC. Ретраи при квоте (3 попытки по 30 сек). |
| `gsc_verify.js` | `.env` + `arr.js` → `gsc_subdomains` | Верификация: проверяет GA код → ANALYTICS → META → FILE. Авто-очищает AUTH_CODE. |
| `gsc_add_sitemap.js` | `.env` + `arr.js` → `gsc_subdomains`, `gsc_sitemap_path` | Добавляет sitemap для каждого поддомена. |

### Google UI (Puppeteer, порт 9227)

| Скрипт | Входные данные | Что делает |
|--------|----------------|------------|
| `gsc_delete_sites.js` | `.env` + `arr.js` → `gsc_sites_to_delete` | Удаляет конкретные сайты из GSC через UI. |
| `gsc_delete_unverified.js` | `.env` + `arr.js` → `gsc_sites_to_delete` | Удаляет **только неподтверждённые** сайты. Требует `GSC_MAIN_RESOURCE` в `.env`. |

---

## 🔧 Типичные проблемы и решения

| Проблема | Причина | Решение |
|----------|---------|---------|
| `❌ Node.js не найден` | Node не установлен | `winget install OpenJS.NodeJS` или скачайте с nodejs.org |
| `❌ Файл arr.js не найден` | Неправильный путь | Проверьте: `scripts/arr.js` относительно места запуска скрипта |
| `❌ OAuth-токен неверен / 401` | Токен истёк | Получите новый на https://oauth.yandex.ru/ или в data_editor |
| `❌ Достигнут лимит сайтов в GSC` | > 1000 сайтов на аккаунт | Удалите неиспользуемые (`gsc_delete_sites.js`) или используйте другой аккаунт |
| `❌ AUTH_CODE недействителен` | Код одноразовый / истёк | Получите новый: запустите `gsc_verify.js` без AUTH_CODE → получите ссылку → вставьте код в `.env` |
| `❌ Браузер не подключается (порт 9229/9227)` | Браузер не запущен / закрыт | Нажмите кнопку запуска браузера в лаунчере, авторизуйтесь, **не закрывайте** |
| `❌ Кнопка не найдена (Puppeteer)` | UI Яндекс/Google изменился | Селекторы в скрипте устарели — нужно обновить под новый UI |
| `❌ Превышен лимит запросов (429)` | Слишком много запросов | Скрипты имеют задержки (500мс–3с), просто подождите |

---

## 📁 История изменений / Лог диалогов

> Этот раздел ведётся вручную. Добавляйте записи при значимых изменениях.

| Дата | Что сделано | Детали |
|------|-------------|--------|
| 2026-09-01 | **Инициализация репозитория** | Создан README, подключён GitHub, настроен git. Перенесены скрипты из старого проекта `C:\Users\haritonov.vs\Desktop\Скрипты\ЯВ&GSC`. |
| 2026-08-20 | Добавлен `yandex_sites_to_delete` | В `arr.js` и `data_editor.py` добавлено поле для удаления сайтов из Яндекс.Вебмастера. |
| 2026-08-19 | `metrika_bind.js` v2 | Переписан поиск фреймов: теперь сканирует все фреймы, ищет `.counter-mirrors-list-item`, кликает только не привязанные. |
| 2026-08-12 | `recomen.js` | Добавлена проверка рекомендаций Яндекса. |
| 2026-08-06 | Базовая структура | Созданы `launcher.py`, `data_editor.py`, основные скрипты для Яндекс и Google. |

---

## 🔗 Полезные ссылки

- [Яндекс.Вебмастер API](https://yandex.ru/dev/webmaster/)
- [Google Search Console API](https://developers.google.com/search-console)
- [Google Site Verification API](https://developers.google.com/site-verification)
- [Puppeteer документация](https://pptr.dev/)
- [googleapis npm](https://www.npmjs.com/package/googleapis)

---

## 📄 Лицензия

Внутренний проект. Использование только в рамках команды.