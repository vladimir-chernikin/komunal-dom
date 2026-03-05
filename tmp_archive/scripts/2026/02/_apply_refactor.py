#!/usr/bin/env python3
"""
Скрипт для применения рефакторинга к main_agent.py
Дата: 2026-02-23
"""

import re

# Путь к файлу
file_path = "/var/www/komunal-dom_ru/main_agent.py"

# Читаем файл
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Файл загружен: {len(content)} символов")

# ============================================================
# ИЗМЕНЕНИЕ 1: Убрать accumulated_fields из ProblemAccumulationService
# ============================================================
old_pattern1 = r"""txtPrb = accumulation_result\['updated_problem'\]
                new_accumulated_fields = accumulation_result\.get\('fields', \{\}\)  # НОВЫЕ поля из сообщения

                # ИСПРАВЛЕНО \(2026-02-16\): ОБЪЕДИНЯЕМ старые и новые accumulated_fields
                # Приоритет: НОВЫЕ поля перезаписывают СТАРЫЕ
                final_accumulated_fields = \{\}
                if accumulated_fields:
                    final_accumulated_fields\.update\(accumulated_fields\)
                    logger\.info\(f"\[DEBUG\] Старые accumulated_fields: \{accumulated_fields\}"\)
                if new_accumulated_fields:
                    final_accumulated_fields\.update\(new_accumulated_fields\)
                    logger\.info\(f"\[DEBUG\] Новые accumulated_fields: \{new_accumulated_fields\}"\)
                accumulated_fields = final_accumulated_fields

                # ИСПРАВЛЕНО \(2026-02-16\): КРИТИЧЕСКИЙ лог ПОСЛЕ объединения accumulated_fields
                logger\.info\(f"\[CRITICAL DEBUG\] ✅ ФИНАЛЬНЫЕ accumulated_fields: \{accumulated_fields\}"\)
                logger\.info\(f"\[CRITICAL DEBUG\] txtPrb: \{txtPrb\}"\)

                if accumulation_result\['is_meaningful'\]:
                    logger\.info\(f"txtPrb обновлен \(содержательный\): '\{txtPrb\[:100\]\.\.\.'"\)
                    logger\.info\(f"Извлеченные поля: \{accumulated_fields\}"\)
                else:
                    logger\.info\(f"txtPrb обновлен \(короткий ответ\): '\{txtPrb\[:100\]\.\.\.'"\)"""

new_text1 = """txtPrb = accumulation_result['updated_problem']
                # ИСПРАВЛЕНО (2026-02-23): accumulated_fields УБРАН!
                # new_accumulated_fields = accumulation_result.get('fields', {})  # УДАЛЕНО!

                logger.info(f"[РЕФАКТОРИНГ] ✅ txtPrb: '{txtPrb[:100]}'")
                logger.info(f"[РЕФАКТОРИНГ] ✅ established_filters: {established_filters}")

                # ИСПРАВЛЕНО (2026-02-23): is_meaningful убран (только логи)
                logger.info(f"txtPrb обновлен: '{txtPrb[:100]}...'")"""

if re.search(old_pattern1, content):
    content = re.sub(old_pattern1, new_text1, content, count=1)
    print("✅ ИЗМЕНЕНИЕ 1 применено: accumulated_fields УБРАН!")
else:
    print("⚠️ ИЗМЕНЕНИЕ 1: pattern не найден (возможно уже применено)")

# ============================================================
# ИЗМЕНЕНИЕ 2: Закомментировать старый SemanticPreCheck
# ============================================================
old_pattern2 = r"""        # ИСПРАВЛЕНО \(2026-02-23\): Старый код SemanticPreCheck закомментирован
        # semantic_check_result = \{\}
        # if self\.filter_detection and self\.ai_agent and txtPrb:
            try:"""

new_text2 = """        # ИСПРАВЛЕНО (2026-02-23): SemanticPreCheck УБРАН! (дублирует первый вызов)
        # semantic_check_result = {}
        # if self.filter_detection and self.ai_agent and txtPrb:
        #     try:"""

if re.search(old_pattern2, content):
    content = re.sub(old_pattern2, new_text2, content, count=1)
    print("✅ ИЗМЕНЕНИЕ 2 применено: старый SemanticPreCheck закомментирован!")
else:
    print("⚠️ ИЗМЕНЕНИЕ 2: pattern не найден")

# ============================================================
# Сохраняем файл
# ============================================================
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n✅ Файл сохранён: {file_path}")
print(f"📊 Размер: {len(content)} символов")
