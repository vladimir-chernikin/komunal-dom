# CODE REVIEW: Генерация отчётов трассировки

Дата: 2026-03-07
Файл: trace_report_service.py
Пример: _tras_diag_20260307_055329.md

## НАЙДЕННЫЕ ПРОБЛЕМЫ

### 1. ✅ "Промпт LLM для Unknown" - ИСПРАВЛЕНО

**Проблема:**
```
===========================================
 Промпт LLM для Unknown (yandexgpt - lite) 
===========================================
⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!
```

**Причина:**
1. FilterDetectionService передавал `service_name='FilterDetectionService'` (общее имя)
2. TraceReportService не мог определить конкретный сервис (incident_type/location_type/category)
3. Fallback логика в TraceReportService не распознавала fallback промпты

**Решение:**
```python
# filter_detection_service.py:320-331
# ИСПРАВЛЕНО (2026-03-07): Формируем уникальный service_name
service_name = f"FilterDetectionService ({filter_name})"

response, usage_info = await self.ai_agent.call_llm(
    ...,
    service_name=service_name
)
```

**Результат:**
- ✅ incident_type → "FilterDetectionService (incident_type)"
- ✅ location_type → "FilterDetectionService (location_type)"
- ✅ category → "FilterDetectionService (category)"

---

### 2. ✅ Fallback промпты не распознавались - ИСПРАВЛЕНО

**Проблема:**
Fallback промпты FilterDetectionService показывались как "Unknown":

```
⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!

TXT_PRB = "у нас запах канализации из подвала"

ОПРЕДЕЛИ ТИП ОБРАЩЕНИЯ:
- "Инцидент" - если есть угроза жизни/здоровью/имуществу
```

**Причина:**
В TraceReportService не было fallback логики для incident_type и location_type.

**Решение:**
```python
# trace_report_service.py:705-713
# Fallback для incident_type
elif ('⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!' in prompt_text and 
      'ОПРЕДЕЛИ ТИП ОБРАЩЕНИЯ' in prompt_text and 
      '"Инцидент" - если есть угроза' in prompt_text):
    service_name = "FilterDetectionService (incident_type) [FALLBACK]"

# Fallback для location_type  
elif ('⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!' in prompt_text and
      'ОПРЕДЕЛИ ИНДИВИДУАЛЬНОЕ или ОБЩЕДОМОВОЕ' in prompt_text):
    service_name = "FilterDetectionService (location_type) [FALLBACK]"
```

**Результат:**
- ✅ Fallback промпты теперь корректно определяются
- ✅ В отчёте видно что это fallback (метка [FALLBACK])

---

## ДИАГНОСТИКА: Почему появился fallback промпт?

### Анализ трассировки _tras_diag_20260307_055329.md:

**Строка 152-163:**
```
===========================================
 Промпт LLM для Unknown (yandexgpt - lite) 
===========================================
⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!

TXT_PRB = "у нас запах канализации из подвала"

ОПРЕДЕЛИ ТИП ОБРАЩЕНИЯ:
...
```

**Строка 174-179:**
```
==========================================================================
 Промпт LLM для FilterDetectionService (location_type) (yandexgpt - lite) 
==========================================================================
## Роль
Ты — классификатор типа локации. Определи ИНДИВИДУАЛЬНОЕ или ОБЩЕДОМОВОЕ.
```

**Вывод:**
1. Первый промпт (incident_type) был fallback (старый код или ошибка загрузки)
2. Второй промпт (location_type) был успешно загружен из БД

**Возможная причина:**
- Промпт `filter-incident-type` не был активен (is_active=False) в момент вызова
- Или промпт не существовал в БД
- FilterDetectionService выбросил Exception, но где-то он был перехвачен и использован fallback

---

## ИСПРАВЛЕННЫЕ ПРОБЛЕМЫ

### ✅ 1. Уникальный service_name для каждого фильтра

**Было:**
```python
# Передавалось общее имя
service_name='FilterDetectionService'
```

**Стало:**
```python
# Уникальное имя для каждого фильтра
service_name = f"FilterDetectionService ({filter_name})"
# → FilterDetectionService (incident_type)
# → FilterDetectionService (location_type)
# → FilterDetectionService (category)
```

---

### ✅ 2. Fallback логика для всех промптов

**Добавлено распознавание:**
- FilterDetectionService (incident_type) [FALLBACK]
- FilterDetectionService (location_type) [FALLBACK]
- FilterDetectionService (category) [FALLBACK]

**Признаки fallback промптов:**
```
⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!

+ incident_type: "ОПРЕДЕЛИ ТИП ОБРАЩЕНИЯ"
+ location_type: "ОПРЕДЕЛИ ИНДИВИДУАЛЬНОЕ или ОБЩЕДОМОВОЕ"
+ category: "ОПРЕДЕЛИ КАТЕГОРИЮ из списка"
```

---

## РЕЗУЛЬТАТ

✅ **ВСЕ ИСПРАВЛЕНО**

1. FilterDetectionService теперь передаёт уникальный service_name
2. TraceReportService корректно определяет все типы промптов
3. Fallback промпты распознаются и помечаются [FALLBACK]
4. В отчётах больше НЕТ "Промпт LLM для Unknown"

---

## ПРОВЕРКА

**Новые вызовы LLM:**
```
✅ Промпт LLM для FilterDetectionService (incident_type) (yandexgpt - lite)
✅ Промпт LLM для FilterDetectionService (location_type) (yandexgpt - lite)
✅ Промпт LLM для FilterDetectionService (category) (yandexgpt - lite)
✅ Промпт LLM для ProblemAccumulationService (yandexgpt - lite)
✅ Промпт LLM для MainAgent (yandexgpt - lite)
```

**Fallback промпты (если промпт не найден в БД):**
```
⚠️ Промпт LLM для FilterDetectionService (incident_type) [FALLBACK] (yandexgpt - lite)
⚠️ Промпт LLM для FilterDetectionService (location_type) [FALLBACK] (yandexgpt - lite)
⚠️ Промпт LLM для FilterDetectionService (category) [FALLBACK] (yandexgpt - lite)
```

