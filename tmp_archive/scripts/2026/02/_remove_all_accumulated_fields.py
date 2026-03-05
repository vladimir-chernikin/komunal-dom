#!/usr/bin/env python3
"""
Полное удаление accumulated_fields из main_agent.py
"""

import re

file_path = "/var/www/komunal-dom_ru/main_agent.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_size = len(content)
print(f"Исходный размер: {original_size} символов")
print(f"accumulated_fields встречается: {content.count('accumulated_fields')} раз")

# ============================================================
# 1. Удаляем accumulated_fields из параметров функций
# ============================================================

# _create_ambiguous_result_from_candidates
old1 = r"async def _create_ambiguous_result_from_candidates\(self, candidates_data: List\[Dict\], original_message: str = \"\", is_followup: bool = False, dialog_history: List\[Dict\] = None, session_id: str = None, established_filters: Dict = None, txtPrb: str = None, accumulated_fields: Dict = None\)"
new1 = "async def _create_ambiguous_result_from_candidates(self, candidates_data, original_message='', is_followup=False, dialog_history=None, session_id=None, established_filters=None, txtPrb=None)"
content = re.sub(old1, new1, content)

# _generate_ai_question
old2 = r"async def _generate_ai_question\(self, context=None, dialog_history=None, candidates=None, established_filters=None, txtPrb=None, question_type=None, session_id=None, accumulated_fields=None\)"
new2 = "async def _generate_ai_question(self, context=None, dialog_history=None, candidates=None, established_filters=None, txtPrb=None, question_type=None, session_id=None)"
content = re.sub(old2, new2, content)

# _generate_smart_clarification
old3 = r"async def _generate_smart_clarification\(self, candidates_with_attrs: List\[Dict\], original_message: str = \"\", is_followup: bool = False, dialog_history: List\[Dict\] = None, txtPrb: str = None, established_filters: Dict = None, session_id: str = None, is_refusal: bool = False, accumulated_fields: Dict = None, txtStopQ: List\[str\] = None\)"
new3 = "async def _generate_smart_clarification(self, candidates_with_attrs, original_message='', is_followup=False, dialog_history=None, txtPrb=None, established_filters=None, session_id=None, is_refusal=False, txtStopQ=None)"
content = re.sub(old3, new3, content)

# ============================================================
# 2. Удаляем accumulated_fields из вызовов функций
# ============================================================

# _generate_ai_question вызовы
old4 = r"await self\._generate_ai_question\(\s*[^)]*accumulated_fields=accumulated_fields\s*\)"
new4 = "await self._generate_ai_question(context=context, dialog_history=dialog_history, candidates=candidates, established_filters=established_filters, txtPrb=txtPrb, question_type=question_type, session_id=session_id)"
content = re.sub(old4, new4, content)

# _create_ambiguous_result_from_candidates вызовы
old5 = r"await self\._create_ambiguous_result_from_candidates\([^)]*accumulated_fields\s*\)"
new5 = "await self._create_ambiguous_result_from_candidates(candidates_data, original_message, is_followup, dialog_history, session_id, established_filters, txtPrb)"
content = re.sub(old5, new5, content)

# _generate_smart_clarification вызовы
old6 = r"await self\._generate_smart_clarification\([^)]*accumulated_fields=accumulated_fields\s*\)"
new6 = "await self._generate_smart_clarification(candidates_with_attrs, original_message, is_followup, dialog_history, txtPrb, established_filters, session_id, is_refusal, txtStopQ)"
content = re.sub(old6, new6, content)

# ============================================================
# 3. Удаляем accumulated_fields из metadata
# ============================================================

old7 = r"'accumulated_fields': accumulated_fields,"
new7 = ""
content = content.replace(old7, new7)

old8 = r"\n\s*'accumulated_fields': accumulated_fields\n"
new8 = ""
content = re.sub(old8, new8, content)

# ============================================================
# 4. Удаляем accumulated_fields из логирования
# ============================================================

old9 = r"logger\.info\(f\"  \[TOOL\] accumulated_fields: \{[^}]*\}\"\)"
new9 = ""
content = re.sub(old9, new9, content)

old10 = r"logger\.info\(f\"  \[TOOL\] accumulated_fields: \{json\.dumps\(accumulated_fields[^)]*\}\"\)"
new10 = ""
content = re.sub(old10, new10, content)

# ============================================================
# 5. Удаляем использование accumulated_fields.get()
# ============================================================

# has_source = accumulated_fields.get('source')
old11 = r"has_source = accumulated_fields\.get\('source'\) is not None"
new11 = "has_source = False  # ИСПРАВЛЕНО (2026-02-23): accumulated_fields удалён"
content = content.replace(old11, new11)

# ============================================================
# Сохраняем
# ============================================================

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

new_size = len(content)
print(f"\nНовый размер: {new_size} символов")
print(f"Удалено: {original_size - new_size} символов")
print(f"accumulated_fields осталось: {content.count('accumulated_fields')} раз")

