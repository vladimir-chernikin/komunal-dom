#!/bin/bash

file="/var/www/komunal-dom_ru/main_agent.py"

# Бекап
cp "$file" "$file.tmp"

# Удаляем блок accumulated_fields в absolute_facts (строки ~3151-3202)
# Находим по уникальной строке и удаляем до следующего блока

python3 << 'PYTHON'
with open('/var/www/komunal-dom_ru/main_agent.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    line_num = i + 1
    
    if i >= skip_until:
        skip_until = -1
    
    # Пропускаем блок if accumulated_fields: (в absolute_facts)
    if 'if accumulated_fields:' in line and i+1 < len(lines) and 'absolute_facts' in lines[i+1]:
        print(f"🗑️ Пропускаем accumulated_fields в absolute_facts: {line_num}")
        # Находим конец блока (когда отступ уменьшается)
        indent = len(line) - len(line.lstrip())
        j = i + 1
        while j < len(lines):
            curr = lines[j]
            if curr.strip() and len(curr) - len(curr.lstrip()) <= indent:
                break
            j += 1
        skip_until = j
        continue
    
    if i < skip_until:
        continue
    
    new_lines.append(line)

with open('/var/www/komunal-dom_ru/main_agent.py', 'w') as f:
    f.writelines(new_lines)

print(f"✅ Обновлено: {len(lines)} -> {len(new_lines)} строк")
print(f"Удалено: {len(lines) - len(new_lines)} строк")
PYTHON

