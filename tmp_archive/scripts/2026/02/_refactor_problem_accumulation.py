#!/usr/bin/env python3
"""
Рефакторинг problem_accumulation_service.py
Убираем fields из JSON возврата
"""

import re

file_path = "/var/www/komunal-dom_ru/problem_accumulation_service.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

print(f"Файл загружен: {len(content)} символов")

# ============================================================
# ИЗМЕНЕНИЕ 1: Убрать fields из docstring
# ============================================================
old_docstring = r"""                'fields': \{              # Извлеченные поля
                    'problem': str \| None,
                    'location': str \| None,
                    'source': str \| None,
                    'category': str \| None,
                    'severity': str \| None,
                    'intensity': str \| None,
                    'object': str \| None
                \}
            \}
        \"\"\""""

new_docstring = """                'db_error': bool         # ИСПРАВЛЕНО (2026-02-05): Ошибка загрузки промпта из БД
            }
        \"\"\""""

if re.search(old_docstring, content):
    content = re.sub(old_docstring, new_docstring, content)
    print("✅ Docstring обновлён")
else:
    print("⚠️ Docstring не найден (возможно другой формат)")

# ============================================================
# ИЗМЕНЕНИЕ 2: Убрать fields из return при отказе
# ============================================================
old_refusal = """            return {
                'updated_problem': current_problem,  # НЕ меняем txtPrb!
                'extracted_info': {},
                'is_meaningful': False,  # Отказ не содержит новой информации о проблеме
                'is_refusal': True,
                'new_info': f"пользователь отказался от услуги '{refused_service}'",
                'db_error': False,  # ИСПРАВЛЕНО (2026-02-05)
                'fields': {},
                'refused_service': refused_service
            }"""

new_refusal = """            return {
                'updated_problem': current_problem,  # НЕ меняем txtPrb!
                'is_refusal': True,
                'refused_service': refused_service,
                'db_error': False  # ИСПРАВЛЕНО (2026-02-23)
            }"""

if old_refusal in content:
    content = content.replace(old_refusal, new_refusal)
    print("✅ Return при отказе обновлён")
else:
    print("⚠️ Return при отказе не найден")

# ============================================================
# ИЗМЕНЕНИЕ 3: Убрать fields из логирования
# =================================================<arg_value>old_log = """            logger.info(f"  [SEARCH] is_meaningful: {result['is_meaningful']}")
            logger.info(f"  [NOTE] new_info: '{result['new_info']}'")
            logger.info(f"  [NOTE] updated_problem: '{result['updated_problem']}'")
            logger.info(f"  🔧 fields: {json.dumps(result['fields'], ensure_ascii=False)}")"""

new_log = """            logger.info(f"  [SEARCH] is_refusal: {result.get('is_refusal', False)}")
            logger.info(f"  [NOTE] updated_problem: '{result['updated_problem']}'")"""

if old_log in content:
    content = content.replace(old_log, new_log)
    print("✅ Логирование обновлено")
else:
    print("⚠️ Логирование не найдено")

# ============================================================
# ИЗМЕНЕНИЕ 4: Убрать fields из _parse_llm_response
# ============================================================
old_parse = """            # Валидация полей
            return {
                'updated_problem': result.get('updated_problem', current_problem),
                'extracted_info': {},
                'is_meaningful': result.get('is_meaningful', False),
                'new_info': result.get('new_info', ''),
                'fields': {
                    'problem': result.get('fields', {}).get('problem'),
                    'location': result.get('fields', {}).get('location'),
                    'source': result.get('fields', {}).get('source'),
                    'category': result.get('fields', {}).get('category'),
                    'severity': result.get('fields', {}).get('severity'),
                    'intensity': result.get('fields', {}).get('intensity'),
                    'object': result.get('fields', {}).get('object')
                }
            }"""

new_parse = """            # Валидация полей
            return {
                'updated_problem': result.get('updated_problem', current_problem),
                'is_refusal': False,
                'db_error': False
            }"""

if old_parse in content:
    content = content.replace(old_parse, new_parse)
    print("✅ _parse_llm_response обновлён")
else:
    print("⚠️ _parse_llm_response не найден")

# ============================================================
# ИЗМЕНЕНИЕ 5: Убрать fields из exception handler
# ============================================================
old_exception = """            return {
                'updated_problem': current_problem,
                'extracted_info': {},
                'is_meaningful': False,
                'new_info': '',
                'db_error': False,  # ИСПРАВЛЕНО (2026-02-05)
                'fields': {
                    'problem': None,
                    'location': None,
                    'source': None,
                    'category': None,
                    'severity': None,
                    'intensity': None,
                    'object': None
                }
            }"""

new_exception = """            return {
                'updated_problem': current_problem,
                'is_refusal': False,
                'db_error': False
            }"""

if old_exception in content:
    content = content.replace(old_exception, new_exception)
    print("✅ Exception handler обновлён")
else:
    print("⚠️ Exception handler не найден")

# ============================================================
# Сохраняем
# ============================================================
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n✅ Файл сохранён: {file_path}")
print(f"📊 Новый размер: {len(content)} символов")
