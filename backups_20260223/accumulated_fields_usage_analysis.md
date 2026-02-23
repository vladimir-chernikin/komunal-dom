# АНАЛИЗ ИСПОЛЬЗОВАНИЯ accumulated_fields в main_agent.py

## 1. ПРОВЕРКА location_known

**Файл:** main_agent.py
**Строки:** 826, 933, 1852

```python
location_known = accumulated_fields.get('location') is not None

if not location_known and incident_type != 'Запрос':
    # Генерируем вопрос "Где именно?"
    ai_result = await self._generate_ai_question(
        context=context,
        question_type='location',
        accumulated_fields=accumulated_fields
    )
```

**ИСПОЛЬЗУЕТСЯ ДЛЯ ХАРДКОДА ВОПРОСА:**
- ✅ ДА - если location=None, генерируется вопрос "Где именно?"

---

## 2. ПРОВЕРКА severity_known / intensity_known

**Файл:** main_agent.py
**Строки:** 1857-1858, 934, 2989

```python
severity_known = accumulated_fields.get('severity') is not None
intensity_known = accumulated_fields.get('intensity') is not None

needs_severity_clarification = (
    is_incident and
    is_water_problem and
    has_source and
    not (severity_known or intensity_known)
)

if needs_severity_clarification:
    # Генерируем вопрос "Как сильно течет?"
    context = f"Нужно уточнить СТЕПЕНЬ ПРОТЕЧКИ (как сильно течет/протекает)"
    ai_result = await self._generate_ai_question(...)
```

**ИСПОЛЬЗУЕТСЯ ДЛЯ ХАРДКОДА ВОПРОСА:**
- ✅ ДА - если severity=None и intensity=NULL, генерируется вопрос про степень течи

---

## 3. ПРОВЕРКА has_source

**Файл:** main_agent.py
**Строки:** 938, 1864, 2992

```python
has_source = accumulated_fields.get('source') is not None
source = (accumulated_fields.get('source') or '').lower()

is_water_problem = (
    category in ['Водоснабжение', 'Отопление', 'Канализация'] and
    category_confidence >= 0.7
)

# has_source используется вместе с water_problem для определения needs_severity_clarification
needs_severity_clarification = (
    is_incident and
    is_water_problem and
    has_source and  # ← ТРЕБУЕТСЯ source!
    not (severity_known or intensity_known)
)
```

**ИСПОЛЬЗУЕТСЯ ДЛЯ ХАРДКОДА ВОПРОСА:**
- ✅ ДА - косвенно: has_source=True водит к вопросу про степень течи

---

## 4. ЗАПРЕТ ПОВТОРНЫХ ВОПРОСОВ (forbidden_questions)

**Файл:** main_agent.py
**Строки:** 3303-3325

```python
if accumulated_fields and accumulated_fields.get('location'):
    location_value = accumulated_fields['location']
    logger.info(f"Location ЯВНО извлечена из текста: '{location_value}' - запрещаем спрашивать")
    forbidden_questions.append('location')
```

**ИСПОЛЬЗУЕТСЯ ДЛЯ ХАРДКОДА ВОПРОСА:**
- ✅ ДА - если location извлечён, ЗАПРЕЩАЕТ спрашивать "Где?"

---

## 5. ABSOLUTE FACTS ДЛЯ LLM

**Файл:** main_agent.py
**Строки:** 5020-5043

```python
known = []
if accumulated_fields:
    for key, value in accumulated_fields.items():
        if value and key != 'category':
            if key == 'location':
                known.append(f"Локация: {value}")
            elif key == 'object':
                known.append(f"Объект: {value}")
            elif key == 'problem':
                known.append(f"Проблема: {value}")
            elif key == 'source':
                known.append(f"Источник: {value}")
            elif key == 'severity':
                known.append(f"Серьёзность: {value}")
            elif key == 'intensity':
                known.append(f"Интенсивность: {value}")

absolute_facts = '\n'.join(known) if known else ""
```

**ИСПОЛЬЗУЕТСЯ ДЛЯ ХАРДКОДА ВОПРОСА:**
- ✅ ДА - передаётся в LLM, LLM НЕ задаёт вопросы об известном

---

## 6. ПРОВЕРКА object_known

**Файл:** main_agent.py
**Строки:** НЕТ!

**Результат поиска:**
```
grep -n "object_known" main_agent.py
# Ничего не найдено
```

**ИСПОЛЬЗУЕТСЯ ДЛЯ ХАРДКОДА ВОПРОСА:**
- ❌ НЕТ - `object` НЕ используется для решения задавать вопрос или нет!

**КРИТИЧНАЯ ПРОБЛЕМА:**
- `object` НЕ проверяется на None
- Бот НЕ знает, нужно ли спрашивать "Что сломалось?"
- Поэтому задаёт глупые вопросы "Что именно сломалось?" даже когда object="труба"

---

## ИТОГОВАЯ ТАБЛИЦА

| Поле | Используется для хардкода вопроса | Строки кода | Тип проверки |
|------|-----------------------------------|-------------|--------------|
| `location` | ✅ ДА | 826, 933, 1852 | location_known = ... is not None |
| `severity` | ✅ ДА | 1857, 934, 2989 | severity_known = ... is not None |
| `intensity` | ✅ ДА | 1858, 934, 2989 | intensity_known = ... is not None |
| `source` | ✅ ДА | 938, 1864 | has_source = ... is not None |
| `object` | ❌ НЕТ | - | НЕ ПРОВЕРЯЕТСЯ! |
| `problem` | ⚠️ Косвенно | 5028 | Только для absolute_facts |
| `category` | ❌ НЕТ | - | НЕ используется из fields |

---

## КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### 1. `object` НЕ ИСПОЛЬЗУЕТСЯ

**Проблема:**
- accumulated_fields.object извлекается (когда работает)
- НО НИГДЕ не проверяется на None
- Бот НЕ знает, нужно ли спрашивать "Что сломалось?"

**Результат в диалоге:**
```
"из трубы" → fields:
  source: "труба"  # Неправильно!
  object: null

Бот думает: object=null → спрашивает "Что именно сломалось?"
```

### 2. `source` ИСПОЛЬЗУЕТСЯ НЕПРАВИЛЬНО

**Проблема:**
- `source` = "откуда течёт" (потолок, соседи, стояк)
- LLM заполняет `source` значением "труба" (это object!)
- has_source=True включает needs_severity_clarification

**Результат:**
- "из трубы" → source="труба" → has_source=True → water_problem=True
- needs_severity_clarification=True → "Каков характер течи: непрерывный или периодический?"

---

## РЕКОМЕНДАЦИИ

### 1. ДОБАВИТЬ ПРОВЕРКУ object_known

```python
# После строки 1852 добавить:
object_known = accumulated_fields.get('object') is not None

# Использовать для решения задавать вопрос:
if not object_known and not location_known:
    # Спрашиваем "Что именно сломалось и где?"
```

### 2. РАЗДЕЛИТЬ object И source

**В промпте ProblemAccumulationService:**
- `object` = объект проблемы (труба, кран, батарея)
- `source` = откуда исходит (потолок, соседи, стояк)

### 3. ИСПРАВИТЬ ЛОГИКУ needs_severity_clarification

```python
# Было:
needs_severity_clarification = (
    is_incident and
    is_water_problem and
    has_source and  # ← source может быть="труба"!
    not (severity_known or intensity_known)
)

# Должно быть:
needs_severity_clarification = (
    is_incident and
    is_water_problem and
    object_known and  # ← object должен быть!
    not (severity_known or intensity_known)
)
```

---

Генерировано: 2026-02-23
