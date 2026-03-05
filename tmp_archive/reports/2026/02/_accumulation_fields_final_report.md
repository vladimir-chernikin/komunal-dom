# ФИНАЛЬНЫЙ ОТЧЁТ - accumulated_fields

## ОТВЕТ НА ВОПРОС 1: ИСПОЛЬЗУЮТСЯ ЛИ ПОЛЯ ДЛЯ ХАРДКОДА ВОПРОСОВ?

### ✅ ДА, ИСПОЛЬЗУЮТСЯ!

| Поле | Хардкод вопроса | Строки | Логика |
|------|-----------------|--------|--------|
| **`location`** | ✅ ДА | 826, 933, 1852 | `if not location_known → "Где именно?"` |
| **`severity`** | ✅ ДА | 1857, 934, 2989 | `if not severity_known → вопрос про степень` |
| **`intensity`** | ✅ ДА | 1858, 934, 2989 | `if not intensity_known → вопрос про степень` |
| **`source`** | ✅ ДА | 938, 1864, 2992 | `has_source=True → needs_severity_clarification` |
| **`object`** | ❌ НЕТ | - | **НЕ ПРОВЕРЯЕТСЯ!** |
| **`problem`** | ⚠️ Косвенно | 5028 | Только для absolute_facts |
| **`category`** | ❌ НЕТ | - | Используется из established_filters |

---

## ДЕТАЛЬНЫЙ АНАЛИЗ

### 1. location → "Где именно?"

```python
# main_agent.py:826
location_known = accumulated_fields.get('location') is not None

if not location_known and incident_type != 'Запрос':
    # Генерируем вопрос
    context = "Нужно уточнить локацию."
    ai_result = await self._generate_ai_question(
        context=context,
        question_type='location',
        accumulated_fields=accumulated_fields
    )
```

**Результат:**
- location=None → "Где именно это произошло?"
- location="ванная" → вопрос НЕ задаётся

---

### 2. severity/intensity → "Как сильно течет?"

```python
# main_agent.py:1857-1884
severity_known = accumulated_fields.get('severity') is not None
intensity_known = accumulated_fields.get('intensity') is not None

has_source = accumulated_fields.get('source') is not None

is_water_problem = (
    category in ['Водоснабжение', 'Отопление', 'Канализация'] and
    category_confidence >= 0.7
)

needs_severity_clarification = (
    is_incident and
    is_water_problem and
    has_source and  # ← ТРЕБУЕТСЯ source!
    not (severity_known or intensity_known)
)

if needs_severity_clarification:
    context = "Нужно уточнить СТЕПЕНЬ ПРОТЕЧКИ (как сильно течет/протекает)"
    ai_result = await self._generate_ai_question(...)
```

**Результат:**
- severity=None, intensity=None, source="труба" → "Каков характер течи: непрерывный или периодический?"
- severity="сильная" ИЛИ intensity="непрерывная" → вопрос НЕ задаётся

---

### 3. object → НЕ ИСПОЛЬЗУЕТСЯ!

**КРИТИЧЕСКАЯ ПРОБЛЕМА:**

```python
# В коде НЕТ проверки:
# object_known = accumulated_fields.get('object') is not None
```

**Результат:**
- object="труба" → бот всё равно спрашивает "Что именно сломалось?"
- object=null → бот спрашивает "Что именно сломалось?"

**Бот НЕ РАЗЛИЧАЕТ эти состояния!**

---

### 4. source → ИСПОЛЬЗУЕТСЯ НЕПРАВИЛЬНО!

**Проблема:**
```
"из трубы" → fields:
  source: "труба"  # LLM думает source=объект!
  object: null
```

**Логика:**
```python
has_source = accumulated_fields.get('source') is not None
# has_source=True → включает needs_severity_clarification
```

**Результат:**
- source="труба" → has_source=True → water_problem=True
- needs_severity_clarification=True
- Генерируется: "Каков характер течи: непрерывный или периодический?"

**ПРОБЛЕМА:** source должен быть "откуда" (потолок, соседи), а не "что" (труба, кран)!

---

## ОТВЕТ НА ВОПРОС 2: БЕКАПЫ СОЗДАНЫ

### ✅ ФАЙЛЫ БЕКАПА:

| Файл | Путь | Размер |
|------|------|--------|
| **Промпт** | `/var/www/komunal-dom_ru/prompts_backup/problem-accumulation-service_ID6_BEFORE_FIX_20260223_163008.txt` | 6.6 KB |
| **Сервис** | `/var/www/komunal-dom_ru/backups_20260223_133420/problem_accumulation_service.py` | 27 KB |
| **MainAgent** | `/var/www/komunal-dom_ru/backups_20260223_133420/main_agent.py` | 347 KB |
| **Анализ** | `/var/www/komunal-dom_ru/backups_20260223/accumulated_fields_usage_analysis.md` | - |

### 📊 Структура бекапа:

```
/var/www/komunal-dom_ru/
├── prompts_backup/
│   └── problem-accumulation-service_ID6_BEFORE_FIX_20260223_163008.txt
└── backups_20260223_133420/
    ├── problem_accumulation_service.py
    ├── main_agent.py
    └── accumulated_fields_usage_lines.txt
```

---

## КРИТИЧЕСКИЕ ПРОБЛЕМЫ В АНАЛИЗИРУЕМОМ ДИАЛОГЕ

### ЦЕПОЧКА СОБЫТИЙ:

```
1. Пользователь: "у меня капает"
   → accumulated_fields:
      source: null
      object: null  # ← НЕ извлечён

2. Пользователь: "из трубы"
   → accumulated_fields:
      source: "труба"  # ← НЕПРАВИЛЬНО! "труба" это object
      object: null

3. MainAgent видит:
   → water_problem=True (category=Водоснабжение)
   → has_source=True (source="труба")
   → severity_known=False, intensity_known=False
   → needs_severity_clarification=True

4. _generate_ai_question:
   context: "Нужно уточнить СТЕПЕНЬ ПРОТЕЧКИ"
   LLM генерирует: "Каков характер течи: непрерывный или периодический?"
```

### КОРНЕВЫЕ ПРИЧИНЫ:

1. **ProblemAccumulationService НЕ извлекает object**
   - Промпт НЕ упоминает поле `object`
   - LLM НЕ знает про это поле
   - object всегда NULL

2. **source используется вместо object**
   - source = "откуда течёт" (потолок, соседи)
   - Но LLM заполняет source="труба" (объект!)
   - Это включает needs_severity_clarification

3. **Нет проверки object_known**
   - MainAgent НЕ проверяет accumulated_fields.object
   - Бот НЕ знает, нужно ли спрашивать "Что сломалось?"
   - Задаёт глупые вопросы

---

## РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ

### 1. ИСПРАВИТЬ ПРОМПТ ProblemAccumulationService

**Добавить в JSON schema:**
```json
{
  "object": "объект проблемы (труба, кран, батарея, розетка, дверь)",
  "source": "откуда исходит проблема (потолок, соседи сверху, стояк, фасад)",
  "location": "где находится объект (ванная, кухня, подъезд, двор)",
  "problem": "что произошло (течет, капает, не работает, сломалось)",
  "severity": "насколько серьёзно (сильная, слабая, средняя)",
  "intensity": "характер проявления (непрерывная, периодическая, редкая)"
}
```

**Примеры:**
```
"течет из трубы в ванной" →
  object: "труба"
  source: null
  location: "ванная"
  problem: "течет"
  severity: null
  intensity: null

"капает с потолка на кухне" →
  object: "потолок"
  source: "соседи сверху"
  location: "кухня"
  problem: "капает"
  severity: null
  intensity: "периодическая"
```

### 2. ДОБАВИТЬ ПРОВЕРКУ object_known В main_agent.py

**После строки 1852:**
```python
# Проверяем object
object_known = accumulated_fields.get('object') is not None

# Если объект НЕ известен → спрашиваем
if not object_known and not location_known:
    context = "Нужно уточнить, ЧТО именно сломалось."
    ai_result = await self._generate_ai_question(
        context=context,
        question_type='object',
        accumulated_fields=accumulated_fields
    )
    return {...}
```

### 3. ИСПРАВИТЬ needs_severity_clarification

**Было (строка 1879):**
```python
needs_severity_clarification = (
    is_incident and
    is_water_problem and
    has_source and  # ← source может быть="труба"!
    not (severity_known or intensity_known)
)
```

**Должно быть:**
```python
needs_severity_clarification = (
    is_incident and
    is_water_problem and
    has_source and source in ['потолок', 'сосед', 'стояк', 'фасад'] and  # ← проверка значения!
    not (severity_known or intensity_known)
)
```

**ИЛИ:**
```python
needs_severity_clarification = (
    is_incident and
    is_water_problem and
    object_known and object in ['труба', 'батарея', 'кран'] and  # ← object!
    not (severity_known or intensity_known)
)
```

### 4. УБРАТЬ source ИЗ fields

**Причина:**
- source путается с object
- LLM не понимает разницу
- Лучше использовать только object

**Альтернатива:**
- Переименовать source в damage_source (источник повреждения)
- Добавить чёткое описание: "откуда исходит проблема (НЕ объект!)"

---

## СЛЕДУЮЩИЕ ШАГИ

1. ✅ Бекапы созданы
2. ⏳ Исправить промпт ProblemAccumulationService
3. ⏳ Добавить проверку object_known в main_agent.py
4. ⏳ Исправить логику needs_severity_clarification
5. ⏳ Протестировать на диалоге

---

Генерировано: 2026-02-23
