#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
СКРИПТ ДЛЯ ДОБАВЛЕНИЯ SITEMAP
Работает с arr.js в формате пользователя
Отчет только в CMD (без сохранения файлов)
"""

import requests
import os
import sys
import time
import re

print("=" * 70)
print("🚀 ЗАПУСК СКРИПТА: Добавление Sitemap в Яндекс Вебмастер")
print("=" * 70)
print()

# 1. НАЙТИ ARR.JS
arr_path = None
search_paths = [
    # "Массивы/arr.js",
    "arr.js", 
    "../Скрипты/arr.js",
    "./Скрипты/arr.js"
]

for path in search_paths:
    if os.path.exists(path):
        arr_path = os.path.abspath(path)
        print(f"✅ Найден файл: {arr_path}")
        break

if not arr_path:
    print("❌ Файл arr.js не найден!")
    print("Положите arr.js в папку 'Массивы'")
    sys.exit(1)

# 2. ПРОСТОЙ ПАРСИНГ - читаем весь файл
try:
    with open(arr_path, 'r', encoding='utf-8') as f:
        content = f.read()
except Exception as e:
    print(f"❌ Ошибка чтения файла: {e}")
    sys.exit(1)

# 3. ИЗВЛЕЧЬ YANDEX SETTINGS
oauth_token = None
user_id = None
sitemap_name = None

# Ищем блок yandexSettings
if 'yandexSettings = {' in content:
    start_idx = content.find('yandexSettings = {')
    
    # Ищем конец блока
    brace_count = 0
    in_brace = False
    end_idx = start_idx
    
    for i in range(start_idx, len(content)):
        char = content[i]
        
        if char == '{':
            brace_count += 1
            in_brace = True
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and in_brace:
                end_idx = i + 1
                break
    
    if end_idx > start_idx:
        settings_block = content[start_idx:end_idx]
        
        # Ищем значения
        token_match = re.search(r"oauth_token:\s*['\"]([^'\"]+)['\"]", settings_block)
        if token_match:
            oauth_token = token_match.group(1)
        
        id_match = re.search(r"user_id:\s*['\"]([^'\"]+)['\"]", settings_block)
        if id_match:
            user_id = id_match.group(1)
        
        name_match = re.search(r"sitemap_name:\s*['\"]([^'\"]+)['\"]", settings_block)
        if name_match:
            sitemap_name = name_match.group(1)

# 4. ИЗВЛЕЧЬ МАССИВ LINKS (игнорируя комментарии)
links = []

if 'const links = [' in content:
    # Находим начало массива
    start_idx = content.find('const links = [')
    
    # Ищем конец массива
    end_idx = content.find('];', start_idx)
    if end_idx == -1:
        next_const = content.find('const ', start_idx + 15)
        if next_const != -1:
            end_idx = next_const
        else:
            end_idx = content.find('module.exports', start_idx)
            if end_idx == -1:
                end_idx = len(content)
    
    if end_idx > start_idx:
        array_content = content[start_idx:end_idx]
        
        # Разбиваем на строки
        lines = array_content.split('\n')
        
        for line in lines:
            # Пропускаем закомментированные строки
            if line.strip().startswith('//'):
                continue
            
            # Убираем комментарии в середине строки
            if '//' in line:
                line = line.split('//')[0].strip()
            
            # Ищем строки в кавычках
            single_matches = re.findall(r"'([^']+)'", line)
            for match in single_matches:
                match = match.strip()
                if match and not match.startswith('//'):
                    links.append(match)
            
            double_matches = re.findall(r'"([^"]+)"', line)
            for match in double_matches:
                match = match.strip()
                if match and not match.startswith('//'):
                    links.append(match)

# Убираем дубликаты и пустые строки
links = [link.strip() for link in links if link.strip()]
links = list(dict.fromkeys(links))

# 5. ПРОВЕРКА ДАННЫХ
if not oauth_token:
    print("❌ Не найден oauth_token в arr.js")
    sys.exit(1)

if not user_id:
    print("❌ Не найден user_id в arr.js")
    sys.exit(1)

if not sitemap_name:
    sitemap_name = 'sitemaps'

print("✅ Данные из arr.js загружены:")
print(f"   • Яндекс User ID: {user_id}")
print(f"   • Имя файла sitemap: {sitemap_name}")
print(f"   • Найдено поддоменов: {len(links)}")
print()

if not links:
    print("❌ Нет поддоменов для обработки!")
    sys.exit(1)

# 6. ФУНКЦИЯ ДОБАВЛЕНИЯ SITEMAP
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

# 7. ОБРАБОТКА ВСЕХ ПОДДОМЕНОВ
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

# 8. ФИНАЛЬНЫЙ ОТЧЕТ В CMD
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

# 9. КРАТКИЕ РЕКОМЕНДАЦИИ
print("\n💡 КРАТКИЕ РЕКОМЕНДАЦИИ:")

if not_found > 0:
    print(f"• {not_found} сайтов не найдены - добавьте их в Яндекс Вебмастер")

if already > 0:
    print(f"• {already} sitemap уже были добавлены - это нормально")

print("=" * 70)

# 10. ПАУЗА ДЛЯ EXE (чтобы увидеть результаты)
if hasattr(sys, 'frozen'):
    input("\nНажмите Enter для выхода...")