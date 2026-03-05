#!/usr/bin/env python3
import re

file_path = "/var/www/komunal-dom_ru/problem_accumulation_service.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_until = None
i = 0

while i < len(lines):
    line = lines[i]
    
    # Пропускаем строки 64-67 (is_meaningful, extracted_info, new_info)
    if i == 63:  # Перед is_meaningful
        # Добавляем только нужное
        new_lines.append("                'is_refusal': bool,      # Является ли сообщением отказом\n")
        new_lines.append("                'refused_service': str,  # Отвергнутая услуга (если is_refusal=True)\n")
        new_lines.append("                'db_error': bool         # Ошибка загрузки промпта из БД\n")
        i += 5  # Пропускаем 4 строки (64-67)
        continue
    
    # Удаляем строки 88-89, 91-93 из return (is_meaningful, extracted_info, new_info)
    if i == 87 and "'is_meaningful'" in line:
        new_lines.append("                'is_refusal': True,\n")
        new_lines.append("                'refused_service': refused_service,\n")
        i += 7  # Пропускаем до fields
        # Удаляем 'fields': {},
        if "'fields'" in lines[i]:
            i += 1
        continue
    
    # Удаляем строку с fields из return
    if "'fields'" in line and '}' in line:
        i += 1
        continue
    
    # Удаляем логирование fields (линию с "🔧 fields:")
    if "🔧 fields:" in line:
        i += 1
        continue
    
    # Удаляем логирование is_meaningful, extracted_info, new_info
    if "is_meaningful" in line and "result" in line:
        i += 3  # Пропускаем 3 строки логирования
        continue
    
    new_lines.append(line)
    i += 1

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✅ Обновлено: {file_path}")
print(f"Было: {len(lines)} строк")
print(f"Стало: {len(new_lines)} строк")
