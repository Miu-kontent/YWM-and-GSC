# YWM-and-GSC — Яндекс Вебмастер и Google Search Console

Автоматизация рутинных задач в **Яндекс.Вебмастере**, **Яндекс.Метрике** и **Google Search Console**.

Русскоязычный внутренний проект: коммиты, документация и интерфейс — на русском.

---

## Возможности

- **Десктоп-приложение** (pywebview) с веб-интерфейсом: вкладки, формы, лог выполнения в реальном времени, итоговые таблицы с копированием, тёмная/светлая тема.
- **Единая авторизация аккаунтами:** Яндекс OAuth (токен получается из браузера) и Google OAuth Desktop — без ручного ввода токенов.
- **Яндекс:** официальный API (Вебмастер v4/v4.1, Метрика Management) + браузерные скрипты (Playwright через CDP, порт 9229): регионы, чеклист, привязка зеркал, «Обход по счётчикам».
- **Google:** Search Console API (webmasters v3, siteVerification v1): добавление, верификация, сайтмапы, переотправка, удаление.

### Возможности интерфейса

- Категории и подкатегории скриптов с **бейджами метода** (`API` / `Browser`).
- Ввод данных прямо на странице скрипта (ссылки, города, пути sitemap, селекты режимов, чекбоксы опций).
- **Предзапусковая валидация** — запуск блокируется с уведомлением, если не хватает данных.
- Консоль выполнения + **сводка и таблица результатов** в реальном времени (статусные маркеры: добавлено ранее, успешно, новое, ошибка).
- Пост-кнопки: «Копировать сайты для переотправки» — собирает в буфер сайты с проблемными статусами сайтмапов.
- Статусная подсветка рамок скрипта/категории во время выполнения.
- Авто-проверка обновлений с GitHub (splash-экран).

---

## Установка

### Вариант 1 — установщик (рекомендуется)

Запустите `Установщик YWM-and-GSC.bat`. Он:

1. Устанавливает Python 3.11+ при необходимости (тихая установка).
2. Предлагает выбрать папку и создаёт внутри каталог `YWM-and-GSC/`.
3. Скачивает проект с GitHub и распаковывает.
4. Создаёт виртуальное окружение `.venv` и ставит зависимости: `pywebview`, `requests`, `python-dotenv`, `websocket-client`, `playwright`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`.
5. Создаёт `yandex/app_config.json` и `google/app_config.json` — OAuth-конфиги приложений, которых нет в git.
6. Создаёт ярлык **YWM-and-GSC** на рабочем столе (включая привязку иконки) и удаляет сам себя.

После установки запускайте ярлык на рабочем столе — он ведёт на `ЯВМ и GSC.exe` (компиляция не требуется).

### Вариант 2 — вручную

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install pywebview requests python-dotenv websocket-client playwright google-auth google-auth-oauthlib google-api-python-client
```

Запуск:

```bash
python -B utils\main.py
```

### Требования

- Windows 10/11 (WebView2 есть по умолчанию).
- Только **Chrome**: для браузерных скриптов он запускается кнопкой «Браузер» прямо из GUI с remote-debugging.

> Playwright ставится как пакет, но браузеры не скачиваются. Скрипты подключаются к запущенному Chrome через CDP: порт **9229** — Яндекс, **9227** — Google.

---

## Начало работы

1. Запустите приложение (ярлык или `python -B utils\main.py`).
2. **Яндекс-аккаунт:** во вкладке «Яндекс» нажмите кнопку запуска браузера (порт 9229), войдите в `webmaster.yandex.ru`, затем нажмите **«Авторизоваться»** — токен, логин и `user_id` сохранятся в `yandex/accounts.json`, активный аккаунт запишется в `yandex/config.json`.
3. **Google-аккаунт:** аналогично через порт 9227: войдите в Google, нажмите **«Авторизоваться»** — откроется OAuth-окно Google (Desktop flow), доступ сохранится в `google/accounts.json`, активный аккаунт — в `google/config.json`.
4. Выберите скрипт в категории, при необходимости заполните данные (или оставьте пустыми — многие скрипты обрабатывают тогда **все сайты аккаунта**) и нажмите **«Запустить»**.

---

## Структура проекта

```text
YWM-and-GSC/
├── yandex/                    # Модуль Яндекса
│   ├── scripts/               # Python-скрипты (yandex_*.py)
│   │   └── yandex_client.py   # Общий модуль: аккаунты + подмеш. oauth_token/user_id
│   ├── registry.json          # Реестр категорий/скриптов для GUI
│   ├── app_config.json        # OAuth-конфиг (gitignored, создаёт установщик)
│   ├── config.json            # active_account, metric_id, contact_path, sitemap_path
│   ├── accounts.json          # login -> {oauth_token, user_id} (gitignored)
│   └── arrays/                # Данные скриптов: array_*.json
├── google/                    # Модуль Google
│   ├── scripts/               # Python-скрипты (gsc_*.py)
│   │   └── gsc_client.py      # Общий модуль: credentials, services, утилиты
│   ├── registry.json          # Реестр категорий/скриптов для GUI
│   ├── app_config.json        # OAuth Desktop-конфиг (gitignored, создаёт установщик)
│   ├── config.json            # active_account, sitemap_path
│   ├── accounts.json          # email -> {access_token, refresh_token, token_expiry}
│   └── arrays/                # Данные скриптов: array_*.json
├── gui/                       # Веб-интерфейс (pywebview)
│   ├── index.html             # Разметка (splash, карточки, формы, логи, таблицы)
│   ├── style.css              # Стили (тёмная/светлая тема, статусная подсветка)
│   ├── script.js              # Клиентская логика (реестр, запуск, стриминг логов)
│   └── favicon.ico
├── utils/
│   ├── main.py                # Ядро приложения (Api, подпроцессы, OAuth, обновления)
│   └── version.json           # Версия для авто-обновлений
├── ЯВМ и GSC.exe              # .NET-лаунчер (gitignored; ярлык целится на него)
├── Launcher.cs                # Исходник лаунчера (gitignored)
├── Установщик YWM-and-GSC.bat # Установщик (gitignored, раздаётся отдельно)
├── AGENTS.md                  # Контекст проекта для AI-ассистентов (gitignored)
└── .gitignore
```

---

## Скрипты

Формат входа практически единый: `links` — список сайтов **с протоколом или без** (пусто = все сайты аккаунта). Для списков и опций у скриптов есть свои поля на странице.

### Яндекс

| Категория | Скрипт | Метод | Назначение |
|---|---|---|---|
| **Выгрузка** | `yandex_export` | API | Выгрузка сайтов Вебмастера + опции: «Индексация», «Сайтмапы», «Проверки» (diagnostics) |
| | `yandex_metrika_export` | API | Выгрузка счётчиков Метрики и статусов привязки сайтов |
| **Сайты** | `yandex_add_sites` | API | Добавление сайтов в Вебмастер (список обязателен) |
| | `yandex_verify` | API / Browser | Подтверждение прав: META_TAG → HTML_FILE → DNS (API) или «Подтвердить» в UI (браузер) |
| | `yandex_sites_to_delete` | API | Удаление сайтов из Вебмастера (список обязателен) |
| | `yandex_region_add` | Browser | Добавление/проверка региона (поля `links` + `city`; пусто = проверка всех) |
| | `yandex_checklist` | Browser | Чеклист: «Рекомендации» и «Ошибки» с кнопками «Проверить» (API-диагностика + UI параллельно) |
| **Сайтмапы** | `yandex_add_sitemap` | API | Добавление сайтмапа всем сайтам (путь из конфига) |
| | `yandex_sitemap_recrawl` | API | Переотправка сайтмапа на переобход (опция «проверять лимиты»; HTTP 202 = отправлено) |
| | `yandex_delete_sitemap` | API | Удаление сайтмапа (поле «Путь сайтмапа» на странице скрипта) |
| **Счётчики** | `yandex_metrika_add_mirrors` | API | Добавление сайтов в счётчик Метрики |
| | `yandex_metrika_bind_mirrors` | Browser | Привязка зеркал счётчика к Вебмастеру + чинка статусов (пусто = все непривязанные) |
| | `yandex_metrika_add_metrics` | Browser | Включение «Обход по счётчикам» |
| | `yandex_metrika_delete_mirrors` | API | Удаление сайтов **строго по списку** (обязателен; партии по 50 с ретраями) |
| **Тесты** | `yandex_export_test` | API | Тестовая выгрузка всех данных сайта |
| | `yandex_sitemap_test` | API | Проверка сайтмапов и проблем сайта (распараллелено, 6 потоков) |
| | `yandex_metrika_test` | API | Диагностика счётчика Метрики |

### Google

| Категория | Скрипт | Метод | Назначение |
|---|---|---|---|
| **Выгрузка** | `gsc_export` | API | Выгрузка сайтов (права) + «Сайтмапы» (чекбокс) со статусами; пост-кнопка копирования для переотправки |
| **Сайты** | `gsc_add_sites` | API | Добавление сайтов в GSC (URL-prefix; уже из списка не дублируются) |
| | `gsc_verify` | API | Верификация: webResource insert META → FILE; авто-определение уже подтверждённых |
| | `gsc_delete_sites` | API | Удаление сайтов (список обязателен) |
| **Сайтмапы** | `gsc_add_sitemap` | API | Добавление сайтмапа + «здоровье» существующих; пост-кнопка «В переотправку» |
| | `gsc_resend_sitemap` | API | Переотправка: режим `submit` / `delete_and_submit` |
| | `gsc_delete_sitemap` | API | Удаление сайтмапа (поле «Путь сайтмапа» на странице скрипта) |
| **Тесты** | `gsc_export_test` | API | Тестовая выгрузка: sites, sitemaps, searchanalytics, urlInspection, webResource |
| | `gsc_sitemap_test` | API | Проверка сайтмапов: статусы, errors/warnings, contents |

> Служебные модули `yandex_client.py`, `gsc_client.py` и служебные `*_test`-хелперы скрыты из интерфейса (реестр `excludedScripts`), но вызываются скриптами напрямую.

---

## Конфигурация и данные

| Файл | Что хранит | Создаётся |
|---|---|---|
| `yandex/app_config.json` | `client_id` Яндекса для OAuth-потока | установщиком |
| `yandex/config.json` | активный аккаунт, `metric_id`, `contact_path`, `sitemap_path` | приложением |
| `yandex/accounts.json` | аккаунты: логин → токен и `user_id` | кнопкой «Авторизоваться» |
| `yandex/arrays/<script>.json` | данные конкретного скрипта | приложением (сам, при отсутствии — `{}`) |
| `google/app_config.json` | блок `installed` OAuth-клиента GSC | установщиком |
| `google/config.json` | активный аккаунт, `sitemap_path` | приложением |
| `google/accounts.json` | аккаунты: email → access/refresh-токен | кнопкой «Авторизоваться» |
| `google/arrays/<script>.json` | данные конкретного скрипта | приложением |

Скрипты читают конфиги через общие модули `yandex_client.py` / `gsc_client.py`:
- Яндекс: `load_config()` возвращает `config.json` **с подмешанными** `oauth_token`/`user_id` активного аккаунта.
- Google: `get_credentials()` автоматически обновляет access-токен по `token_expiry` и пишет обратно в `accounts.json`.

---

## Запуск и порты

- URL браузеров с remote-debugging: `http://127.0.0.1:9229` (Яндекс), `http://127.0.0.1:9227` (Google).
- Браузерные скрипты используют Playwright `connect_over_cdp` — тот же профиль, что и ручной вход (логин сохраняется между сессиями).
- API-скрипты не требуют браузера, только токены активного аккаунта.
- Скрипты одного сервиса запускаются последовательно, Яндекс и Google — параллельно.

---

## Настройка под свои аккаунты

Ключи OAuth-приложений живут в `yandex/app_config.json` и `google/app_config.json` (создаёт установщик). Чтобы использовать собственные приложения:

- **Яндекс** — в консоли `oauth.yandex.ru` создайте приложение «WEB», получите `client_id`, впишите его в `yandex/app_config.json`.
- **Google** — в Google Cloud Console создайте OAuth Desktop Client и заполните блок `installed` в `google/app_config.json`.

---

## Безопасность

- Секретов в коде нет: все конфиги и массивы — вне git (`.gitignore`).
- В git не попадают: `yandex/config.json`, `yandex/accounts.json`, `yandex/array_*.js`, `google/config.json`, `google/accounts.json`, `google/app_config.json`, `Launcher.cs`, `Установщик YWM-and-GSC.bat`, а также все legacy JS-скрипты Puppeteer (`*.js`).
- При выкладке issue/PR убирайте чувствительные данные.

---

## Разработка

```bash
# проверка синтаксиса всех модулей ядра
python -B -m py_compile utils\main.py yandex\scripts\*.py google\scripts\*.py

# запуск приложения
python -B utils\main.py
```

### История версий

- **2.4.1** — статусная подсветка рамок GUI; удаление сайтов/сайтмапов в Google; browser-режим подтверждения прав Яндекса; плейсхолдеры полей; упрощение delete_mirrors; автономный установщик (без requirements.txt и Node.js); отключён dev-режим окна.
- **2.3.x** — Google: полный API-конвейер (add/verify/add_sitemap/delete/resend/export); авторизация Desktop OAuth и аккаунты; переотправка sitemap.
- **2.2.x** — Яндекс: регионы, чеклист, переотправка sitemap, тесты; категоризация GUI.
- **2.1.x** — Метрика через API (bind/export/delete/add_mirrors, обход), аккаунты Яндекса.
- **2.0** — переход на Python + pywebview (+ Playwright CDP); отказ от Puppeteer/Node.js.

---

_Связанные планы и история решений — в `AGENTS.md` (не коммитится)._