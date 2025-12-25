#!/usr/bin/env python3
import re
import os

# Файлы для исправления
files_to_fix = [
    'tag_search_service.py',
    'semantic_search_service.py', 
    'trigram_search_service.py',
    'tag_search_service_v2.py'
]

for filename in files_to_fix:
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Заменяем SQL запросы
        content = re.sub(
            r'FROM services\b',
            'FROM services_catalog sc',
            content
        )
        
        # Заменяем SELECT с services
        content = re.sub(
            r'SELECT[^;]+FROM services\b',
            'SELECT sc.service_id as id, sc.scenario_name as name, rc.category_name as category, sc.object_type, sc.incident_type, sc.location_type, sc.tags, sc.keywords FROM services_catalog sc LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id',
            content
        )
        
        # Заменяем WHERE s.is_active на WHERE sc.is_active  
        content = re.sub(r'WHERE s\.is_active', 'WHERE sc.is_active', content)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"Исправлен: {filename}")
    else:
        print(f"Файл не найден: {filename}")
