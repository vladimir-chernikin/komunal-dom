#!/usr/bin/env python3
"""Удаление хардкодов из main_agent.py"""

file_path = "/var/www/komunal-dom_ru/main_agent.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip_mode = None
skip_until = None
i = 0

while i < len(lines):
    line = lines[i]
    line_num = i + 1
    
    # ============================================================
    # БЛОК 1: location_known (строки 826-856)
    # ============================================================
    if line_num == 826:  # location_known = ...
        # Находим конец if not location_known:
        j = i
        indent_level = len(line) - len(line.lstrip())
        while j < len(lines):
            curr_line = lines[j]
            # Если строка с меньшим отступом и не пустая - конец блока
            if curr_line.strip() and len(curr_line) - len(curr_line.lstrip()) <= indent_level:
                if not curr_line.strip().startswith('#'):
                    break
            # Нашёл return - конец блока
            if 'return {' in curr_line:
                skip_until = j + 1
                break
            j += 1
        
        print(f"🗑️ Пропускаем location_known блок: {i+1}-{skip_until}")
        i = skip_until
        continue
    
    # ============================================================
    # БЛОК 2: needs_severity_clarification (строки ~1857-2013)
    # ============================================================
    if 'severity_known' in line and 'accumulated_fields' in line and '=' in line:
        # Нашли начало блока needs_severity_clarification
        # Ищём конец: return с AMBIGUOUS
        j = i
        while j < min(i + 200, len(lines)):  # Максимум 200 строк
            if "'status': 'AMBIGUOUS'" in lines[j] and 'needs_severity_clarification' in lines[min(j+1, len(lines)-1)]:
                skip_until = j + 5  # Пропускаем до конца return
                print(f"🗑️ Пропускаем needs_severity_clarification блок: {i+1}-{skip_until}")
                i = skip_until
                break
            j += 1
        if skip_until:
            skip_until = None
            continue
    
    # ============================================================
    # БЛОК 3: accumulated_fields в forbidden_questions (3303-3325)
    # ============================================================
    if line_num >= 3300 and line_num <= 3330 and 'forbidden_questions.append' in line and 'location' in line:
        # Пропускаем 2-3 строки
        print(f"🗑️ Пропускаем forbidden_questions (location): {line_num}")
        i += 3
        continue
    
    # ============================================================
    # Если не попали в пропуск - добавляем строку
    # ============================================================
    new_lines.append(line)
    i += 1

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"\n✅ Обновлено: {file_path}")
print(f"Было: {len(lines)} строк")
print(f"Стало: {len(new_lines)} строк")
print(f"Удалено: {len(lines) - len(new_lines)} строк")
