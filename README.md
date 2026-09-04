# YWM-and-GSC — Яндекс Вебмастер и Google Search Console

Автоматизация рутинных задач в **Яндекс.Вебмастере** и **Google Search Console** через Puppeteer (UI-автоматизация) и Google API / Яндекс API.

> 🇷🇺 **Язык проекта:** русский. Коммиты, документация и диалоги — на русском.

---

## 📦 Что внутри

### 🎯 Основные возможности

| Категория | Скрипты | Описание |
|-----------|---------|----------|
| **Яндекс — Подтверждение прав** | `yandex_verify.js` | Умная верификация: META_TAG → HTML_FILE. Авто-ретраи, понятные ошибки. |
| **Яндекс — Регионы** | `addRegions.js` | Массовое добавление регионов поддоменам. Берёт город из `city[]`, контакт из `contactPath`. |
| **Яндекс — Метрика** | `metrika_bind.js` | Привязка поддоменов к счётчику Яндекс.Метрики. |
| **Яндекс — Обход по счётчикам** | `addMetrics.js` | Включает «Обход по счётчикам» в настройках индексирования. |
| **Яндекс — Sitemap** | `sitemap.py` | Добавление sitemap через Яндекс API (OAuth). |
| **Яндекс — Переобход** | `reindex.js`, `recrawl.js` | Переобход страниц / перезапрос sitemap. |
| **Яндекс — Проверки** | `Regi.js`, `metriks.js`, `recomen.js`, `errors.js` | Проверка региона, обхода счётчиков, рекомендаций, ошибок. |
| **Яндекс — Удаление** | `yandex_sites_to_delete.js` | Удаление поддоменов из Яндекс.Вебмастера. |
| **Google — Добавление сайтов** | `gsc_add_sites.js` | Массовое добавление поддоменов в GSC через Google API (OAuth2). Ретраи при квоте. |
| **Google — Верификация** | `gsc_verify.js` | Умная верификация: ANALYTICS → META → FILE. Проверяет наличие GA кода на сайте. Авто-очистка auth_code. |
| **Google — Sitemap** | `gsc_add_sitemap.js` | Добавление sitemap в GSC. |
| **Google — Удаление (UI)** | `gsc_delete_sites.js`, `gsc_delete_unverified.js` | Удаление сайтов / удаление **неподтверждённых** сайтов из GSC (Puppeteer, порт 9227). |
| **Утилиты** | `userid.js` | Получение `user_id` по OAuth-токену для Яндекс API. |

---

## 🏗 Архитектура (актуальная на 2026-09-04)

```
YWM-and-GSC/
├── yandex/                     # Модуль Яндекс.Вебмастера
│   ├── scripts/                # JS скрипты автоматизации (13 файлов)
│   │   ├── yandex_verify.js
│   │   ├── addRegions.js
│   │   ├── metrika_bind.js
│   │   ├── addMetrics.js
│   │   ├── sitemap.py
│   │   ├── reindex.js
│   │   ├── recrawl.js
│   │   ├── Regi.js
│   │   ├── metriks.js
│   │   ├── recomen.js
│   │   ├── errors.js
│   │   ├── yandex_sites_to_delete.js
│   │   └── userid.js
│   ├── config.json             # Токены Яндекс (OAuth, User ID, Metric ID, Sitemap, Contact Path)
│   ├── array_<script>.js       # Изолированные массивы для каждого скрипта
│   └── loadConfig.js           # Загрузчик конфигов
├── google/                     # Модуль Google Search Console
│   ├── scripts/                # JS скрипты автоматизации (6 файлов)
│   │   ├── gsc_add_sites.js
│   │   ├── gsc_verify.js
│   │   ├── gsc_add_sitemap.js
│   │   ├── gsc_delete_sites.js
│   │   ├── gsc_delete_unverified.js
│   │   └── loadGoogleConfig.js # Хелпер загрузки google/config.json
│   ├── config.json             # Ключи Google (Client ID, Secret, Tokens, Sitemap Path, Main Resource, Redirect URI)
│   ├── array_<script>.js       # Изолированные массивы для каждого скрипта
│   └── loadConfig.js           # Загрузчик массивов
├── gui/                        # Веб-интерфейс (pywebview)
│   ├── index.html              # Разметка (Splash, вкладки, формы, логи, таблицы)
│   ├── style.css               # Стили (тёмная/светлая тема, CSS-переменные, универсальные компоненты)
│   └── script.js               # Клиентская логика (вкладки, запуск, стриминг логов, отчёты)
├── utils/                      # Точка входа и служебные файлы
│   ├── main.py                 # Python ядро (pywebview, Api, subprocess, логи, авто-обновления)
│   └── version.json            # Версия для авто-обновлений
├── .venv/                      # Виртуальное окружение Python (в корне)
├── node_modules/               # Зависимости Node.js (в корне)
├── package.json                # npm deps: puppeteer, googleapis
├── requirements.txt            # Python deps: pywebview, requests, python-dotenv
├── README.md                   # Этот файл
├── AGENTS.md                   # Контекст для AI-ассистентов
├── DEVELOPMENT_PLAN.md         # План разработки (не в git)
├── .gitignore
└── .opencode/
    └── memory/
        └── dialogue.md         # История диалогов
```

---

## 🔐 Хранение данных и конфигурация

### Изоляция по сервисам
Каждый сервис имеет **свой** `config.json` и **свои** `array_<script>.js`:

| Путь | Содержимое |
|------|------------|
| `yandex/config.json` | `oauth_token`, `user_id`, `metricCounterId`, `contactPath`, `sitemap_path` |
| `google/config.json` | `client_id`, `client_secret`, `access_token`, `refresh_token`, `auth_code`, `redirect_uri`, `sitemap_path`, `main_resource` |
| `yandex/array_<script>.js` | Данные только для конкретного Яндекс-скрипта |
| `google/array_<script>.js` | Данные только для конкретного Google-скрипта |

### Принципы
- **Никакого общего `arr.js`** — каждый скрипт получает только нужные ему поля
- **Секреты не в гите** — все `config.json` и `array_*.js` в `.gitignore`
- **GUI генерирует массивы** — при запуске скрипта `utils/main.py` создаёт актуальные `array_<script>.js` из сохранённых данных

### Пример `yandex/config.json`
```json
{
  "oauth_token": "y0_AgAAA...",
  "user_id": "123456789",
  "metricCounterId": "12345678",
  "contactPath": "contacts",
  "sitemap_path": "/sitemap.xml",
  "scripts_data": {
    "yandex_verify": { "links": ["sub.domain.ru"] },
    "addRegions": { "links": ["sub.domain.ru"], "city": ["Москва"] }
  }
}
```

### Пример `google/config.json`
```json
{
  "client_id": "xxx.apps.googleusercontent.com",
  "client_secret": "GOCSPX-...",
  "access_token": "ya29.a0A...",
  "refresh_token": "1//...",
  "auth_code": "",
  "redirect_uri": "http://localhost:3000/",
  "sitemap_path": "/sitemap/",
  "main_resource": "https://medcentr-cristall.ru/",
  "scripts_data": {
    "gsc_add_sites": { "gsc_subdomains": ["https://sub.domain.ru/"] },
    "gsc_verify": { "gsc_subdomains": ["https://sub.domain.ru/"] }
  }
}
```

> ⚠️ **Важно:** `yandex/config.json`, `google/config.json`, `yandex/array_*.js`, `google/array_*.js` — в `.gitignore`. Хранятся локально.

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Python
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Node.js
npm install
```

### 2. Запуск приложения

```bash
# Из виртуального окружения
python utils\main.py
```

### 3. Работа в интерфейсе

1. **Splash Screen** — авто-проверка обновлений с GitHub
2. **Главная (Дашборд)** — выбор сервиса (Яндекс/Google), ввод общих токенов
3. **Страница Яндекс / Google** — верхний блок ключей сервиса, выбор скрипта, ввод поддоменов под конкретный скрипт, кнопка «Запустить»
4. **Параллельный запуск** — Яндекс и Google скрипты могут работать одновременно (subprocess)
5. **Вывод результатов** — консоль в реальном времени + итоговая таблица с копированием

---

## 🖥 GUI (pywebview) — основные элементы

### Вкладки
- **🏠 Главная** — дашборд с карточками сервисов, единая форма ключей доступа
- **🌏 Яндекс** — ключи Яндекса (сводка), список скриптов с полями ввода
- **🔍 Google** — ключи Google (сводка), список скриптов с полями ввода

### Универсальные компоненты (CSS)
- **Grid** — `.grid`, `.grid--responsive`, `.grid--2-cols`
- **Card** — `.card`, `.card--interactive`, `.card__header`, `.card__body`, `.card__icon`
- **Button** — `.btn`, `.btn--primary`, `.btn--secondary`, `.btn--small`, `.btn--icon`
- **Form** — `.form-group`, `.form-label`, `.form-control` (input, textarea)
- **Nav** — `.nav`, `.nav__item` (горизонтальная/вертикальная)
- **Table** — `.table-wrapper`, `.table`
- **Logs** — `.logs-container`, `.log-line` (цвета: success/error/warning/info)

### Темы
- Тёмная (по умолчанию) / Светлая — переключение кнопкой в хедере, сохранение в `localStorage`

---

## 📋 Список скриптов (детально)

### Яндекс (Puppeteer, порт 9229)

| Скрипт | Поля в `array_<script>.js` | Назначение |
|--------|----------------------------|------------|
| `yandex_verify.js` | `links`, `yandexSettings` | Верификация: META_TAG → HTML_FILE. Отчёт: новые/уже было/ошибки |
| `addRegions.js` | `links`, `city`, `contactPath` | Массовое добавление регионов |
| `metrika_bind.js` | `metricCounterId` | Привязка поддоменов к счётчику Метрики |
| `addMetrics.js` | `links`, `yandexSettings` | Включение «Обход по счётчикам» |
| `sitemap.py` | `links`, `yandexSettings` | Sitemap через Яндекс API (OAuth) |
| `reindex.js` | `links` | Переобход страниц |
| `recrawl.js` | `links`, `yandexSettings` | Перезапрос sitemap |
| `Regi.js` | `links` | Проверка региона |
| `metriks.js` | `links`, `metricCounterId` | Проверка обхода счётчиков |
| `recomen.js` | `links` | Проверка рекомендаций |
| `errors.js` | `links` | Проверка ошибок |
| `yandex_sites_to_delete.js` | `yandex_sites_to_delete` | Удаление сайтов из Вебмастера |
| `userid.js` | `yandexSettings.oauth_token` | Получение `user_id` по токену |

### Google API (используют `google/config.json`)

| Скрипт | Поля в `array_<script>.js` | Назначение |
|--------|----------------------------|------------|
| `gsc_add_sites.js` | `gsc_subdomains` | Массовое добавление в GSC. Ретраи при квоте (3×30 сек) |
| `gsc_verify.js` | `gsc_subdomains` | Умная верификация: проверяет GA код → ANALYTICS → META → FILE. Авто-очищает auth_code |
| `gsc_add_sitemap.js` | `gsc_subdomains`, `gsc_sitemap_path` | Добавление sitemap для каждого поддомена |

### Google UI (Puppeteer, порт 9227)

| Скрипт | Поля в `array_<script>.js` | Назначение |
|--------|----------------------------|------------|
| `gsc_delete_sites.js` | `gsc_sites_to_delete` | Удаление конкретных сайтов через UI |
| `gsc_delete_unverified.js` | `gsc_sites_to_delete` | Удаление **только неподтверждённых** сайтов. Требует `main_resource` в конфиге |

---

## ⚙️ Ключевые решения и ограничения

| Проблема | Решение |
|----------|---------|
| Секреты в коде | Изолированные `config.json` в папках сервисов + `.gitignore` |
| UI Яндекс/Google меняется | Селекторы в Puppeteer могут устареть — обновление под новый UI |
| Лимиты API | Ретраи: 500мс (Яндекс), 3сек (Google API), 30сек при квоте |
| Авторизация Google | `gsc_verify.js` генерирует ссылку для auth_code, после использования очищает конфиг |
| Два браузера одновременно | Разные порты (9229/9227) и профили |
| Изоляция данных скриптов | Каждый скрипт имеет свой `array_<script>.js` |

---

## 🔒 Безопасность

- **Никогда** не коммитьте `yandex/config.json`, `yandex/array_*.js`, `google/config.json`, `google/array_*.js`!
- Все секреты исключены через `.gitignore`.
- При создании issue/PR уберите чувствительные данные.

---

## 🔮 Планы развития (миграция на Python + Playwright)

> **Статус:** принято решение, в процессе планирования (см. `DEVELOPMENT_PLAN.md`)

| Этап | Описание | Срок |
|------|----------|------|
| **1. Пилот** | Переписать `metrika_bind.js` + `yandex_verify.js` на Python + Playwright. Создать базовые утилиты: `browser.py`, `selectors.py`, `stealth.py` | 2–3 дня |
| **2. Общие утилиты** | Вынести логику ретраев, логирования, работы с конфигами в `yandex/utils/` | 2 дня |
| **3. Пакетная миграция** | По 2–3 скрипта в день: Regions → Metrics → Sitemap → Checks → Delete | 5–7 дней |
| **4. Google API** | Переписать `gsc_add_sites`, `gsc_verify`, `gsc_add_sitemap` на Python + googleapis | 2 дня |
| **5. Google UI** | Playwright вместо Puppeteer для `gsc_delete_*` | 2 дня |
| **6. Очистка** | Удалить `node_modules/`, `package.json`, все `.js` скрипты, обновить `requirements.txt` | 1 день |

**Anti-detect стратегия:**
- Базовый stealth init script → `playwright-stealth` при необходимости → Camoufox/Nodriver fallback

**Сборка .exe** — планируется отдельно после стабилизации (PyInstaller / Nuitka).

---

## 📁 История изменений / Лог диалогов

| Дата | Что сделано | Детали |
|------|-------------|--------|
| 2026-09-04 | **Рефакторинг GUI** | Универсальные компоненты (Grid, Card, Button, Form, Nav, Table), новая цветовая схема, центрирование заголовков, debug=False |
| 2026-09-04 | **Объединение Google конфигов** | `config.json` + `.env` → один `google/config.json`, удалён `.env`, обновлены все 5 скриптов, `loadGoogleConfig.js` |
| 2026-09-02 | **Полный рефакторинг архитектуры** | pywebview + веб-интерфейс, изоляция Яндекс/Google модулей, изолированные массивы для каждого скрипта, `utils/main.py` ядро |
| 2026-09-02 | **Миграция на Playwright (решено)** | Полный отказ от Node.js/Puppeteer в пользу Python + Playwright, удалены node_modules, package.json |
| 2026-09-01 | **Инициализация репозитория** | Создан GitHub репо, README, AGENTS.md, .gitignore, перенесены скрипты из старого проекта |

---

## 🔗 Полезные ссылки

- [Яндекс.Вебмастер API](https://yandex.ru/dev/webmaster/)
- [Google Search Console API](https://developers.google.com/search-console)
- [Google Site Verification API](https://developers.google.com/site-verification)
- [Puppeteer документация](https://pptr.dev/)
- [Playwright документация](https://playwright.dev/python/)
- [googleapis npm](https://www.npmjs.com/package/googleapis)
- [pywebview](https://pywebview.flowrl.com/)

---

## 📄 Лицензия

Внутренний проект. Использование только в рамках команды.