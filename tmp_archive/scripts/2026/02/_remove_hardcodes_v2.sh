#!/bin/bash

file="/var/www/komunal-dom_ru/main_agent.py"

# Бекап
cp "$file" "$file.backup_before_hardcodes"

# Удаляем блок needs_severity_clarification (строки 1879-2013)
# Начинаем поиск по метке
python3 << 'PYTHON'
import re

with open('/var/www/komunal-dom_ru/main_agent.py', 'r') as f:
    content = f.read()

# Находим и удаляем блок needs_severity_clarification
pattern = r'# ИСПРАВЛЕНО \(2026-02-14\): Проверяем серьёзность ПЕРЕД созданием заявки.*?# \(?s\)ИСПРАВЛЕНО \(2026-02-17\): Диагностика - какой return сработал'

content_new = re.sub(pattern, '# БЛОК needs_severity_clarification УДАЛЁН (2026-02-23)\n            # Логика передана в LLM Orchestrator', content, flags=re.DOTALL)

if len(content_new) < len(content):
    with open('/var/www/komunal-dom_ru/main_agent.py', 'w') as f:
        f.write(content_new)
    print("✅ needs_severity_clarification удалён")
else:
    print("⚠️ needs_severity_clarification не найден")

print(f"Было: {len(content)} символов")
print(f"Стало: {len(content_new)} символов")
PYTHON

