# AGENTS.md — контекст проекта «YWM-and-GSC»

> Этот файл загружается автоматически при каждом старте сессии. Здесь собрана сводка проекта: архитектура, модули, запуск, ключевые решения и история трудностей.

---

## 📌 Проект

**Название:** YWM-and-GSC (Яндекс Вебмастер и Google Search Console)  
**Цель:** Автоматизация рутинных задач в Яндекс.Вебмастере и Google Search Console через Puppeteer (UI-автоматизация) и Google API / Яндекс API.

**Язык проекта:** 🇷🇺 русский — коммиты, документация, диалоги на русском.

---

## 🛠 Стек

| Компонент | Технология |
|-----------|------------|
| Основные скрипты | Node.js (JavaScript) — Puppeteer, googleapis |
| Вспомогательные | Python 3 — requests, python-dotenv (sitemap.py) |
| GUI-лаунчер | Python + CustomTkinter (launcher.py, data_editor.py) |
| Браузеры | Chrome/Chromium с remote debugging (порты 9229, 9227) |
| Хранение данных | `scripts/arr.js` (JS-модуль) + `arrays/.env` (Google OAuth) |

---

## 📂 Структура проекта

```text
YWM-and-GSC/
├── scripts/                    # JavaScript/Python скрипты (21 файл)
│   ├── yandex_verify.js        # Верификация Яндекс (META_TAG → HTML_FILE)
│   ├── addRegions.js           # Добавление регионов поддоменам
│   ├── metrika_bind.js         # Привязка поддоменов к Метрике
│   ├── addMetrics.js           # Включение обхода по счётчикам
│   ├── sitemap.py              # Sitemap через Яндекс API
│   ├── reindex.js              # Переобход страниц
│   ├── recrawl.js              # Перезапрос sitemap
│   ├── Regi.js                 # Проверка региона
│   ├── metriks.js              # Проверка обхода счётчиков
│   ├── recomen.js              # Проверка рекомендаций
│   ├── errors.js               # Проверка ошибок
│   ├── yandex_sites_to_delete.js # Удаление сайтов из Яндекса
│   ├── gsc_add_sites.js        # Добавление сайтов в GSC (API)
│   ├── gsc_verify.js           # Верификация GSC (ANALYTICS → META → FILE)
│   ├── gsc_add_sitemap.js      # Sitemap в GSC (API)
│   ├── gsc_delete_sites.js     # Удаление сайтов из GSC (UI)
│   ├── gsc_delete_unverified.js # Удаление НЕподтверждённых из GSC (UI)
│   ├── userid.js               # Получение user_id по OAuth токену
│   ├── bing_add_sites.js       # (устарело) Добавление в Bing
│   ├── arr.js                  # Данные: links, city, yandexSettings, gsc_subdomains и т.д. (НЕ в git!)
│   └── tokens.json             # (устарело) Токены — в .gitignore!
├── arrays/
│   └── .env                    # Google OAuth: CLIENT_ID, CLIENT_SECRET, ACCESS_TOKEN, AUTH_CODE (НЕ в git!)
├── launcher.py                 # GUI: запуск браузеров, список скриптов, запуск в отдельных окнах
├── data_editor.py              # GUI: редактирование arr.js и .env (вкладки Яндекс/Google/Google API)
├── package.json                # npm deps: googleapis, puppeteer
├── requirements.txt            # Python deps: requests, python-dotenv
├── README.md                   # Полная документация
├── AGENTS.md                   ← этот файл
├── .gitignore
└── .opencode/
    └── memory/
        └── dialogue.md         # История диалогов
```

---

## 🧩 Категории скриптов

### Яндекс (Puppeteer, порт 9229)

| Скрипт | Входные данные | Назначение |
|--------|----------------|------------|
| `yandex_verify.js` | `arr.js` → `links`, `yandexSettings` | Умная верификация: META_TAG → HTML_FILE. Отчёт: новые/уже было/ошибки |
| `addRegions.js` | `arr.js` → `links`, `city`, `contactPath` | Массовое добавление регионов |
| `metrika_bind.js` | `arr.js` → `metricCounterId` | Привязка поддоменов к счётчику Метрики (скан фреймов, скролл) |
| `addMetrics.js` | `arr.js` → `links`, `yandexSettings` | Включение «Обход по счётчикам» |
| `sitemap.py` | `arr.js` → `links`, `yandexSettings` | Sitemap через Яндекс API (OAuth) |
| `reindex.js` / `recrawl.js` | `arr.js` → `links` (+ `yandexSettings`) | Переобход / перезапрос sitemap |
| `Regi.js` / `metriks.js` / `recomen.js` / `errors.js` | `arr.js` → `links` | Проверки: регион, счётчики, рекомендации, ошибки |
| `yandex_sites_to_delete.js` | `arr.js` → `yandex_sites_to_delete` | Удаление сайтов из Вебмастера |

### Google API (требуют `.env`)

| Скрипт | Входные данные | Назначение |
|--------|----------------|------------|
| `gsc_add_sites.js` | `.env` + `arr.js` → `gsc_subdomains` | Массовое добавление в GSC. Ретраи при квоте (3×30 сек) |
| `gsc_verify.js` | `.env` + `arr.js` → `gsc_subdomains` | Умная верификация: проверяет GA код → ANALYTICS → META → FILE. Авто-очищает AUTH_CODE |
| `gsc_add_sitemap.js` | `.env` + `arr.js` → `gsc_subdomains`, `gsc_sitemap_path` | Добавление sitemap для каждого поддомена |

### Google UI (Puppeteer, порт 9227)

| Скрипт | Входные данные | Назначение |
|--------|----------------|------------|
| `gsc_delete_sites.js` | `.env` + `arr.js` → `gsc_sites_to_delete` | Удаление конкретных сайтов через UI |
| `gsc_delete_unverified.js` | `.env` + `arr.js` → `gsc_sites_to_delete` | Удаление **только неподтверждённых** сайтов. Требует `GSC_MAIN_RESOURCE` в `.env` |

---

## ⚙️ Запуск

### 1. Установка зависимостей
```bash
npm install
pip install -r requirements.txt
```

### 2. Подготовка данных
Создайте файлы (НЕ коммитятся в git):
```
scripts/arr.js          # см. шаблон в README.md
arrays/.env             # см. шаблон в README.md
```

### 3. Запуск браузеров (обязательно!)
```bash
python launcher.py
```
Нажмите в GUI:
1. **🌏 Яндекс (порт 9229)** — авторизуйтесь в Вебмастере и Метрике, **не закрывайте**
2. **🔍 Google (порт 9227)** — авторизуйтесь в Search Console, **не закрывайте**

### 4. Запуск скриптов
- Через GUI (launcher.py) — клик по скрипту
- Вручную:
  ```bash
  node scripts/yandex_verify.js
  node scripts/gsc_add_sites.js
  python scripts/sitemap.py
  ```

---

## ⚠️ Ключевые решения и ограничения

| Проблема | Решение |
|----------|---------|
| Секреты в коде | `arr.js` и `.env` в `.gitignore`. Данные только локально. |
| UI Яндекс/Google меняется | Селекторы в Puppeteer-скриптах могут устареть — нужно обновлять под новый UI |
| Лимиты API | Ретраи с задержками: 500мс (Яндекс), 3сек (Google API), 30сек при квоте (Google) |
| Авторизация Google | `gsc_verify.js` генерирует ссылку для AUTH_CODE, после использования очищает `.env` |
| Два браузера одновременно | Разные порты (9229/9227) и профили (`chrome-debug-yandex` / `chrome-debug-google`) |
| `data_editor.py` сохраняет раздельно | Кнопки «Сохранить Яндекс» / «Сохранить Google» не затирают чужие данные |

---

## 🔒 Безопасность

- **Никогда** не коммитьте `scripts/arr.js`, `arrays/.env`, `scripts/tokens.json`!
- Все секреты исключены через `.gitignore`.
- При создании issue/PR уберите чувствительные данные.

---

## 📝 Текущие задачи

<!-- Обновляйте при каждой сессии -->

- [x] Инициализация репозитория GitHub
- [x] Написание README.md и AGENTS.md
- [x] Создание .opencode/memory/dialogue.md
- [ ] Перенос скриптов из старого проекта в новый репозиторий (по мере необходимости)
- [ ] Настройка CI/CD (опционально)
- [ ] Рефакторинг общих утилит (загрузка arr.js, .env, обработка ошибок)

---

## 🗂 История диалогов и решённые проблемы

> Записывайте сюда ключевые моменты диалогов, чтобы не объяснять повторно

### Сессия 2026-09-01
- **Инициализация проекта:** создан репозиторий `https://github.com/Miu-kontent/YWM-and-GSC`
- **Изучен старый проект:** `C:\Users\haritonov.vs\Desktop\Скрипты\ЯВ&GSC` — 21 скрипт, `launcher.py`, `data_editor.py`, структура данных
- **Создана документация:** `README.md` (полная), `AGENTS.md` (контекст), `.gitignore`
- **Настроен git:** инициализирован, закоммичен, подключён remote, запушён в `main`
- **Создана память диалогов:** `.opencode/memory/dialogue.md`
- **Старый проект оставлен как источник:** `C:\Users\haritonov.vs\Desktop\Скрипты\ЯВ&GSC` — скрипты будут переноситься по мере необходимости

---

## 🧠 Шаблон записи новых сессий

При каждом новом диалоге добавляйте сюда блок вида:

```markdown
### Сессия YYYY-MM-DD
- **Задача:** ...
- **Решение:** ...
- **Проблема:** ... → решена через ...
- **Коммит:** <hash> — <сообщение>
```