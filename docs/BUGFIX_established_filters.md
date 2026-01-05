# ИСПРАВЛЕНИЕ БАГА: "Нет необходимости уточнять локацию"

**Дата:** 2026-01-05
**Ветка:** feature/tz-26-12-critical-fixes
**Статус:** ✅ ИСПРАВЛЕНО

## Проблема

Бот спрашивал "Укажите адрес места происшествия" даже когда `location_type=Индивидуальное` был УЖЕ установлен с уверенностью 100%.

### Симптомы:

```
Ход 1: "у меня прорвало трубу"
→ FilterDetectionService установил: location_type=Индивидуальное (confidence 1.0)
→ Бот спросил: "Укажите адрес места происшествия" ❌
```

### Корневая причина:

Было **ТРИ** разные ошибки:

1. **Промпт стратегии C** не учитывал `established_filters`
2. **Метод `_ask_ai_clarification`** не передавал `established_filters` в `_generate_ai_question`
3. **Метод `_determine_missing_filter`** проверял неправильные ключи

---

## Исправление 1: Промпт стратегии C

**Файл:** `main_agent.py`
**Строки:** 2824-2834

**Добавлено правило 3:**
```python
3. ИСПРАВЛЕНИЕ (2026-01-05): КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО спрашивать то, что УЖЕ ИЗВЕСТНО:
   - Проверь блок "УСТАНОВЛЕННЫЕ ФИЛЬТРЫ" выше
   - Если фильтр установлен с уверенностью 80%+ → НЕ спрашивай про него!
   - Если location=Индивидуальное (90%) → НЕ спрашивай "Где?"
   - Если category=Водоснабжение (95%) → НЕ спрашивай "Это водоснабжение?"
   - Если object=труба (90%) → НЕ спрашивай "Что именно?"

   ПРИМЕРЫ НАРУШЕНИЙ (НЕ ДЕЛАЙ ТАК):
   - Фильтр: location=Индивидуальное (90%), вопрос: "Где это произошло?" → ЗАПРЕЩЕНО!
   - Фильтр: category=Водоснабжение (95%), вопрос: "Это водоснабжение?" → ЗАПРЕЩЕНО!
   - Фильтр: object=труба (90%), вопрос: "Из чего течет?" → ЗАПРЕЩЕНО!
```

**Аналогичное правило добавлено для всех типов вопросов:**
- `clarification` (стратегия B)
- `what_happened`
- `location`
- `details`

---

## Исправление 2: Передача established_filters в _ask_ai_clarification

**Файл:** `main_agent.py`

### Изменение 1: Вызов в _orchestrate_microservices (строка 1911-1913)

**ДО:**
```python
return await self._ask_ai_clarification(message_text, unique_candidates, dialog_history)
```

**ПОСЛЕ:**
```python
return await self._ask_ai_clarification(
    message_text, unique_candidates, dialog_history, established_filters
)
```

### Изменение 2: Сигнатура метода _ask_ai_clarification (строка 3170-3203)

**ДО:**
```python
async def _ask_ai_clarification(self, message_text: str, candidates: List[Dict], dialog_history: List[Dict]) -> Dict:
    ...
    ai_result = await self._generate_ai_question(
        context=context,
        dialog_history=dialog_history,
        candidates=candidates,
        txtPrb=extracted_txtPrb,
        question_type='clarification'
    )
```

**ПОСЛЕ:**
```python
async def _ask_ai_clarification(
    self,
    message_text: str,
    candidates: List[Dict],
    dialog_history: List[Dict],
    established_filters: Dict = None  # ← ДОБАВЛЕНО
) -> Dict:
    ...
    ai_result = await self._generate_ai_question(
        context=context,
        dialog_history=dialog_history,
        candidates=candidates,
        established_filters=established_filters,  # ← ДОБАВЛЕНО
        txtPrb=extracted_txtPrb,
        question_type='clarification'
    )
```

---

## Исправление 3: Метод _determine_missing_filter

**Файл:** `main_agent.py`
**Строки:** 2322-2327

### Проблема:

Метод проверял неправильные ключи в `established_filters`:

**Ожидал:**
- `established_filters.get('location')` ❌
- `established_filters.get('object')` ❌
- `established_filters.get('incident')` ❌

**А на самом деле:**
- `location_type` ✅
- `object_description` ✅
- `incident_type` ✅

### Исправление:

**ДО:**
```python
has_location = established_filters.get('location')
has_category = established_filters.get('category')
has_object = established_filters.get('object')
has_incident = established_filters.get('incident')
```

**ПОСЛЕ:**
```python
# ИСПРАВЛЕНО (2026-01-05): Используем правильные ключи из established_filters
has_location = established_filters.get('location_type')
has_category = established_filters.get('category')
has_object = established_filters.get('object_description')
has_incident = established_filters.get('incident_type')
```

---

## Результат тестирования

### ДО исправления:

```
Ход 2: "у меня прорвало трубу"
→ established_filters: {
    'location_type': {'value': 'Индивидуальное', 'confidence': 1.0},
    'category': {'value': 'Водоснабжение', 'confidence': 1.0},
    'incident_type': {'value': 'Инцидент', 'confidence': 1.0},
    'object_description': {'value': 'труба прорвало', 'confidence': 1.0}
  }
→ Стратегия C: "Кандидатов слишком много. Мы НЕ знаем параметр: ЛОКАЦИЯ."
→ Бот спросил: "Укажите адрес места происшествия" ❌
```

### ПОСЛЕ исправления:

```
Ход 2: "у меня прорвало трубу"
→ established_filters: {
    'location_type': {'value': 'Индивидуальное', 'confidence': 1.0},
    'category': {'value': 'Водоснабжение', 'confidence': 1.0},
    'incident_type': {'value': 'Инцидент', 'confidence': 1.0},
    'object_description': {'value': 'труба прорвало', 'confidence': 1.0}
  }
→ Стратегия C: "Кандидатов слишком много. Мы НЕ знаем параметр: ТИП."
→ Бот спросил: "Какой тип трубы прорвало?" ✅
```

---

## Commit'ы

1. **084ab19** - "Исправлен промпт стратегии C - теперь учитывает established_filters"
2. **86c55fd** - "Исправлена передача established_filters в _ask_ai_clarification"
3. **1ab4a7a** - "Исправлен метод _determine_missing_filter - использует правильные ключи established_filters"

---

## Остающиеся проблемы

1. **Двойные вопросы с "ИЛИ"** - LLM продолжает генерировать двойные вопросы ("Произошла утечка воды или требуется другое санитарно-техническое вмешательство?"), хотя LLM-валидация их ловит и исправляет.
2. **DialogLoggerService ошибка** - "can't adapt type 'dict'" при записи metadata в dialog_logs

---

## Вывод

Основная проблема **ИСПРАВЛЕНА**. Бот больше НЕ спрашивает про уже известные параметры (локация, категория, объект).

Теперь правильно определяет недостающий параметр и спрашивает только про то, что еще НЕ известно.
