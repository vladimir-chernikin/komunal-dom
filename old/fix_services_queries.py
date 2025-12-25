#!/usr/bin/env python3
"""
Скрипт для исправления SQL запросов во всех микросервисах
"""

import re
import os

def fix_sql_in_file(filename):
    """Исправляет SQL запросы в файле"""
    if not os.path.exists(filename):
        print(f"Файл не найден: {filename}")
        return False

    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Заменяем простые запросы к services
    content = re.sub(
        r'FROM services\s+WHERE is_active',
        'FROM services_catalog sc WHERE sc.is_active',
        content
    )

    # Заменяем сложные SELECT с JOIN для получения полных данных
    old_pattern = r'SELECT\s+[^;]+FROM services\s+WHERE is_active = TRUE'
    new_query = '''SELECT sc.service_id as id, sc.scenario_name as name,
       rc.category_name as category, ro.object_name as object_type,
       rk.kind_name as incident_type, rl.localization_name as location_type,
       '' as tags, '' as keywords
FROM services_catalog sc
LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
LEFT JOIN ref_objects ro ON sc.object_id = ro.object_id
LEFT JOIN ref_service_kinds rk ON sc.kind_id = rk.kind_id
LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
WHERE sc.is_active = TRUE'''

    content = re.sub(old_pattern, new_query, content, flags=re.MULTILINE | re.DOTALL)

    # Заменяем запросы к services с ID
    content = re.sub(
        r'SELECT[^,]+,\s*scenario_name[^FROM]+FROM services_catalog\s+WHERE\s+service_id\s*=\s*%s',
        'SELECT scenario_name FROM services_catalog WHERE service_id = %s',
        content
    )

    # Заменяем оставшиеся FROM services
    content = re.sub(r'FROM services\s+', 'FROM services_catalog sc ', content)

    if content != original_content:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Исправлен: {filename}")
        return True
    else:
        print(f"⏭️  Пропущен: {filename} (нет замен)")
        return False

# Список файлов для исправления
files_to_fix = [
    'tag_search_service.py',
    'semantic_search_service.py',
    'trigram_search_service.py',
    'tag_search_service_v2.py',
    'ai_agent_service.py',
    'enhanced_ai_agent_service.py'
]

print("Начинаю исправление SQL запросов...")
fixed_count = 0

for filename in files_to_fix:
    if fix_sql_in_file(filename):
        fixed_count += 1

print(f"\nИсправлено файлов: {fixed_count}/{len(files_to_fix)}")
print("\nТеперь все микросервисы используют services_catalog!")