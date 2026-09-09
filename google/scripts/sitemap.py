#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
СКРИПТ ДЛЯ ДОБАВЛЕНИЯ SITEMAP
Читает данные из arrays/sitemap.json (генерируется GUI)
Отчет только в CMD (без сохранения файлов)
"""

import requests
import os
import sys
import time
import json

print("=" * 70)
print("🚀 ЗАПУСК СКРИПТА: Добавление Sitemap в Яндекс Вебмастер")
print("=" * 70)
print()

# 1. НАЙТИ arrays/sitemap.json
array_path = os.path.join(os.path.dirname(__file__), '..', 'arrays', 'sitemap.json')
if not os.path.exists(array_path):
    print(f"❌ Файл не найден: {array_path}")
    print("Запустите скрипт из GUI, чтобы данные были созданы.")
    sys.exit(1)

try:
    with open(array_path, 'r', encoding='utf-8') as f:
        script_data = json.load(f)
except Exception as e:
    print(f"❌ Ошибка чтения файла: {e}")
    sys.exit(1)

# 2. ИЗВЛЕЧЬ YANDEX SETTINGS
settings = script_data.get("yandexSettings", {}) or {}
if isinstance(settings, str):
    try:
        settings = json.loads(settings)
    except Exception:
        settings = {}

oauth_token = settings.get("oauth_token", "")
user_id = settings.get("user_id", "")
sitemap_name = settings.get("sitemap_name", "")

# 3. ИЗВЛЕЧЬ МАССИВ LINKS
links = script_data.get("links", []) or []
if isinstance(links, str):
    links = [l.strip() for l in links.split('\n') if l.strip()]

# Убираем дубликаты и пустые строки
links = [link.strip() for link in links if link.strip()]
links = list(dict.fromkeys(links))

# 4. ПРОВЕРКА ДАННЫХ
if not oauth_token:
    print("❌ Не найден oauth_token в массиве sitemap")
    sys.exit(1)

if not user_id:
    print("❌ Не найден user_id в массиве sitemap")
    sys.exit(1)

if not sitemap_name:
    sitemap_name = 'sitemaps'

print("✅ Данные из arrays/sitemap.json загружены:")
print(f"   • Яндекс User ID: {user_id}")
print(f"   • Имя файла sitemap: {sitemap_name}")
print(f"   • Найдено поддоменов: {len(links)}")
print()

if not links:
    print("❌ Нет поддоменов для обработки!")
    sys.exit(1)

# 5. ФУНКЦИЯ ДОБАВЛЕНИЯ SITEMAP
def add_sitemap(subdomain):
    """Добавляет sitemap для поддомена"""
    try:
        sitemap_url = f'https://{subdomain}/{sitemap_name}'
        api_url = f'https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/https:{subdomain}:443/user-added-sitemaps'
        
        headers = {
            'Authorization': f'OAuth {oauth_token}',
            'Content-Type': 'application/json'
        }
        
        data = {'url': sitemap_url}
        
        response = requests.post(api_url, headers=headers, json=data, timeout=30)
        return response.status_code, response.text
        
    except Exception as e:
        return 0, str(e)

# 6. ОБРАБОТКА ВСЕХ ПОДДОМЕНОВ
print("🔄 Начинаю обработку всех поддоменов...")
print("=" * 70)

total = len(links)
success = 0
already = 0
errors = 0
not_found = 0

# Обрабатываем ВСЕ поддомены
for i, domain in enumerate(links, 1):
    domain = domain.strip()
    
    print(f"{i:4d}/{total}: {domain}")
    
    status, response = add_sitemap(domain)
    
    # Анализируем ответ
    if status == 201:
        print("       ✅ Успешно добавлен")
        success += 1
    elif status == 409:
        print("       ℹ️ Уже был добавлен ранее")
        already += 1
    elif status == 404:
        print("       ❌ Сайт не найден в Яндекс Вебмастере")
        not_found += 1
        errors += 1
    elif status == 400 and "host not added" in response.lower():
        print("       ❌ Сайт не добавлен в Яндекс Вебмастер")
        not_found += 1
        errors += 1
    elif status > 0:
        print(f"       ❌ Ошибка {status}")
        errors += 1
    else:
        print(f"       ❌ Сетевая ошибка")
        errors += 1
    
    # Пауза между запросами
    if i < total:
        time.sleep(0.2)

# 7. ФИНАЛЬНЫЙ ОТЧЕТ В CMD
print()
print("=" * 70)
print("📊 ФИНАЛЬНЫЙ ОТЧЕТ:")
print(f"✅ Успешно добавлено новых: {success}")
print(f"ℹ️ Уже были добавлены ранее: {already}")
print(f"❌ Сайты не найдены в Яндекс Вебмастере: {not_found}")
print(f"⚠️  Другие ошибки: {errors - not_found}")
print("-" * 70)
print(f"📋 ВСЕГО ОБРАБОТАНО: {total}")
print(f"🎯 УСПЕШНО (включая уже добавленные): {success + already}")
print(f"❗ ПРОБЛЕМНЫЕ: {errors}")
print("=" * 70)

# 8. КРАТКИЕ РЕКОМЕНДАЦИИ
print("\n💡 КРАТКИЕ РЕКОМЕНДАЦИИ:")

if not_found > 0:
    print(f"• {not_found} сайтов не найдены - добавьте их в Яндекс Вебмастер")

if already > 0:
    print(f"• {already} sitemap уже были добавлены - это нормально")

print("=" * 70)

# 9. ПАУЗА ДЛЯ EXE (чтобы увидеть результаты)
if hasattr(sys, 'frozen'):
    input("\nНажмите Enter для выхода...")