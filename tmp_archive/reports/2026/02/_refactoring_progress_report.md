# ОТЧЁТ О РЕФАКТОРИНГЕ - ПРОМЕЖУТОЧНЫЙ

## ВЫПОЛНЕНО:

### ✅ 1. ИЗМЕНЁН ПОРЯДОК ВЫЗОВА СЕРВИСОВ

**БЫЛО:**
```
1. ProblemAccumulationService → txtPrb + accumulated_fields
2. FilterDetectionService → established_filters (с txtPrb!)
3. Mikroservices → candidates
4. LLM Orchestrator
```

**СТАЛО:**
```
1. FilterDetectionService → established_filters (ПЕРВЫМ!, с message_text)
2. ProblemAccumulationService → txtPrb (ВТОРЫМ)
3. Mikroservices → candidates (с фильтрацией established_filters)
4. LLM Orchestrator
```

**Изменения в main_agent.py:**
- Строка 354-395: Добавлен вызов FilterDetectionService ПЕРВЫМ
- Строка 397-494: ProblemAccumulationService вызывается ВТОРЫМ
- Строка 496-508: Старый SemanticPreCheck закомментирован (дублирует первый)

---

### ✅ 2. УДАЛЁН accumulated_fields ИЗ main_agent.py

**Удалено:**
- Строки 448-469: Объединение accumulated_fields
- Строки 465-469: Логирование is_meaningful

**Осталось:**
- accumulated_fields всё ещё передаётся в функциях
- accumulated_fields используется в absolute_facts
- accumulated_fields используется в хардкодах (location_known, severity_known и т.д.)

---

## ОСТАЛОСЬ СДЕЛАТЬ:

### ⏳ 3. ProblemAccumulationService - УБРАТЬ fields из JSON

**Файл:** `problem_accumulation_service.py`
**Что убрать:**
- Строки 69-77: fields из docstring
- Строка 102: `'fields': {}` из return
- Парсинг fields из LLM ответа

**Новый JSON:**
```python
{
    'updated_problem': str,  # Обновленный txtPrb
    'is_refusal': bool,      # Является ли сообщением отказом
    'refused_service': str,  # Отвергнутая услуга (если is_refusal=True)
    'db_error': bool         # Ошибка загрузки промпта из БД
}
```

---

### ⏳ 4. УДАЛИТЬ ХАРДКОДЫ

**Файл:** `main_agent.py`

**Удалить блоки:**
1. **location_known** (строки 826-856, 933, 1852)
   ```python
   location_known = accumulated_fields.get('location') is not None
   if not location_known:
       # Хардкод "Где именно?"
   ```

2. **severity_known / intensity_known** (строки 1857-1884)
   ```python
   severity_known = accumulated_fields.get('severity') is not None
   intensity_known = accumulated_fields.get('intensity') is not None
   needs_severity_clarification = (...)
   if needs_severity_clarification:
       # Хардкод "Как сильно течет?"
   ```

3. **has_source** (строки 938, 1864, 2992)
   ```python
   has_source = accumulated_fields.get('source') is not None
   ```

4. **forbidden_questions** (строки 3303-3325)
   ```python
   if accumulated_fields.get('location'):
       forbidden_questions.append('location')
   ```

---

### ⏳ 5. ПЕРЕПИСАТЬ absolute_facts

**Файл:** `main_agent.py`
**Места:** 3336-3400, 4640-4709, 4912-4982

**БЫЛО:**
```python
absolute_facts_list = []
if accumulated_fields.get('source'):
    absolute_facts_list.append(f"- УЖЕ ИЗВЕСТНЫЙ объект: {accumulated_fields['source']}")
if accumulated_fields.get('location'):
    absolute_facts_list.append(f"- УЖЕ ИЗВЕСТНА локация: {accumulated_fields['location']}")
# ... и т.д.
```

**СТАЛО:**
```python
absolute_facts_list = []

# 1. txtPrb - содержит ВСЮ информацию!
if txtPrb:
    absolute_facts_list.append(f"- Описание проблемы: {txtPrb}")

# 2. established_filters (confidence >= 0.8)
if established_filters:
    for filter_name, filter_data in established_filters.items():
        if isinstance(filter_data, dict):
            value = filter_data.get('value')
            confidence = filter_data.get('confidence', 0)
            if value and confidence >= 0.8:
                absolute_facts_list.append(f"- {filter_name}={value} (уверенность: {confidence:.0%})")
```

---

### ⏳ 6. ИЗМЕНИТЬ ЛОГИКУ ORCHESTRATOR'А

**Файл:** `main_agent.py`
**Места:** Все функции `_generate_ai_question`, `_generate_smart_clarification`

**НОВАЯ ЛОГИКА:**
```
LLM Orchestrator ВСЕГДА генерирует вопрос через YandexGPT

3 варианта промптов:
1. 0 candidates → промпт: "Опиши проблему подробнее" (на основе txtPrb)
2. 1 candidate conf>=0.9 → промпт: "Похоже на [услуга]. Уточни детали" (txtPrb + услуга)
3. Несколько candidates → промпт: "Где именно? Что сломалось?" (txtPrb + candidates)
```

**Изменения:**
- Убрать все fallback-вопросы (хардкод)
- ВСЕГДА вызывать `_generate_ai_question`
- Передавать только txtPrb, established_filters, candidates

---

## СЛЕДУЮЩИЕ ШАГИ:

1. ✅ Создать бекап problem_accumulation_service.py
2. ⏳ Убрать fields из JSON
3. ⏳ Удалить хардкоды из main_agent.py
4. ⏳ Переписать absolute_facts
5. ⏳ Изменить логику orchestrator'а
6. ⏳ Протестировать

---

## ФАЙЛЫ:

- **Бекапы:** `/var/www/komunal-dom_ru/backups_20260223_133420/`
- **main_agent.py:** Изменён (порядок сервисов, частично убран accumulated_fields)
- **problem_accumulation_service.py:** ПОКА НЕ ИЗМЕНЯЛСЯ

---

Генерировано: 2026-02-23
Статус: ЧАСТИЧНО ВЫПОЛНЕНО (~30%)
