# ДЕТАЛЬНЫЙ АНАЛИЗ СТРУКТУРЫ СИСТЕМЫ

## 1. MessageHandlerService - КЛАСС, НЕ ТАБЛИЦА

**Статус:** АКТИВНО ИСПОЛЬЗУЕТСЯ ✓

**Что это:**
- Python класс в файле `message_handler_service.py`
- ЕДИНАЯ точка входа для ВСЕХ каналов связи
- НЕ таблица БД!

**Используется в:**
- `message_handler/views.py` - веб-чат
- `enhanced_aspect_bot.py` - Telegram бот
- `test_bot_simulator.py` - тестовый бот
- `dialog_trace_service.py` - трассировка

**Методы:**
- `handle_incoming_message()` - обработка входящего
- `get_session_messages()` - история сообщений

**ВЫВОД:** НЕ УДАЛЯТЬ! Это основной оркестратор системы.

---

## 2. MessageLog МОДЕЛЬ и message_handler_messagelog ТАБЛИЦА

**Статус:** АКТИВНО ИСПОЛЬЗУЕТСЯ, 1574 записей

**Что это:**
- `MessageLog` - Django модель в `message_handler/models.py`
- `message_handler_messagelog` - таблица в БД
- Используется для Django Admin интерфейса!

**Функции модели:**
- `__str__` - красивое отображение в админке
- `get_context_history(limit)` - получить историю диалога

**Используется:**
- Django Admin `/admin/` - просмотр логов
- `get_context_history()` - для получения истории в LLM

**МОЯ ОШИБКА:** Хотел удалить модель и таблицу!

**ПРАВИЛЬНОЕ РЕШЕНИЕ (от пользователя):**
- Оставить модель MessageLog как есть
- Оставить таблицу message_handler_messagelog (1574 записей!)
- НЕ удалять!

** ПРОБЛЕМА:** Сейчас MessageHandlerService пишет в dialog_logs, а MessageLog модель читает из message_handler_messagelog. Получается РАЗВОД:

```
MessageHandlerService:
  _log_message() → DialogLoggerService → dialog_logs (запись)

MessageLog модель:
  objects.filter() → message_handler_messagelog (чтение)
```

**РЕШЕНИЕ:**
1. Оставить message_handler_messagelog для истории
2. Писать НОВЫЕ сообщения в ОБЕ таблицы:
   - message_handler_messagelog - для Django Admin
   - dialog_logs - для детальной аналитики

---

## 3. dialog_memory_store - ПОДРОБНАЯ СТРУКТУРА

**НАЗНАЧЕНИЕ:** Память对话а (контекст между сообщениями)

**СТРУКТУРА:**

### Основные идентификаторы:
- `dialog_id` (UUID) - уникальный ID диалога
- `user_id` (integer) - ID пользователя
- `user_name` - имя пользователя (из канала)

### Извлеченный адрес:
- `extracted_street` - улица
- `extracted_house_number` - номер дома
- `extracted_apartment_number` - квартира
- `extracted_entrance` - подъезд

### Память对话а:
- `context_json` (JSONB) - JSON с накопленной информацией:
  ```json
  {
    "problem": "течет",
    "location": "ванная",
    "source": "труба",
    "category": "Водоснабжение",
    "txtPrb": "у пользователя течет из трубы в ванной"
  }
  ```

### Текущее состояние:
- `current_service_id` - выбранная услуга
- `current_service_name` - название услуги
- `previous_services` (JSONB) - список предыдущих услуг

### Метаданные:
- `dialog_status` - статус (active, closed, etc)
- `last_activity_at` - последнее сообщение
- `message_count` - количество сообщений
- `ai_requests_count` - количество запросов к AI

### Время:
- `created_at` - создание
- `updated_at` - обновление

**Кто использует:**
- `DialogMemoryManager` - управляет памятью
- `MainAgent` - читает context_json

**Отличие от dialog_logs:**
- `dialog_memory_store` - 1 запись на диалог (текущее состояние)
- `dialog_logs` - много записей на диалог (история всех сообщений)

**Аналогия:**
- `dialog_memory_store` = переменные в Python программе
- `dialog_logs` = лог-файл с хронологией

---

## 4. Union с приоритетами - ПОДРОБНАЯ ЛОГИКА

**Где находится:** `main_agent.py:1826` (`_orchestrate_microservices`)

### АЛГОРИТМ ПОШАГОВО:

#### Шаг 1: Получить результаты от поисковых сервисов

```python
tag_results = [
    {'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'confidence': 0.95},
    {'service_id': 7, 'service_name': 'Устранение течи', 'confidence': 0.75}
]

vector_results = [
    {'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'confidence': 0.92},
    {'service_id': 26, 'service_name': 'Общедомовой прорыв', 'confidence': 0.88}
]

semantic_results = [
    {'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'confidence': 0.90}
]
```

#### Шаг 2: Добавить приоритеты

```python
# TagSearch: приоритет 1.0 (точный матч по тегам)
all_candidates.append({
    'service_id': 25,
    'confidence': 0.95,
    'priority': 1.0,
    'sources': ['tag_search']
})

# SemanticSearch: приоритет 0.8 (семантический матч)
all_candidates.append({
    'service_id': 25,
    'confidence': 0.90,
    'priority': 0.8,
    'sources': ['semantic_search']
})

# VectorSearch: приоритет 0.6 (нечеткий матч)
all_candidates.append({
    'service_id': 25,
    'confidence': 0.92,
    'priority': 0.6,
    'sources': ['vector_search']
})
```

#### Шаг 3: Дедупликация и расчет финального confidence

```python
# ДЛЯ КАЖДОГО service_id:
# - Находим максимальный confidence
# - Суммируем приоритеты
# - Умножаем confidence на сумму приоритетов

ПРИМЕР ДЛЯ service_id=25:
1. TagSearch: confidence=0.95, priority=1.0
2. SemanticSearch: confidence=0.90, priority=0.8
3. VectorSearch: confidence=0.92, priority=0.6

Максимальный confidence = 0.95
Сумма приоритетов = 1.0 + 0.8 + 0.6 = 2.4
Количество источников = 3

Финальный confidence = 0.95 * (1 + 0.4 * 2) = 0.95 * 1.8 = 1.71 (ограничиваем до 1.0)

РЕЗУЛЬТАТ: service_id=25 → confidence=1.0 (найден 3 сервисами)
```

#### Шаг 4: Сортировка по confidence

```python
unique_candidates = [
    {'service_id': 25, 'confidence': 1.0, 'sources': ['tag', 'semantic', 'vector']},
    {'service_id': 7, 'confidence': 0.75, 'sources': ['tag']},
    {'service_id': 26, 'confidence': 0.88, 'sources': ['vector']}
]

# Сортируем по confidence DESC
sorted_candidates = [25, 26, 7]
```

#### Шаг 5: Принятие решения

```python
if len(unique_candidates) == 1 and confidence >= 0.9:
    → SUCCESS (подтвердить)
elif len(unique_candidates) <= 10:
    → AI уточнение (какой именно?)
else:
    → "Что случилось?" (слишком много)
```

---

## 5. UNION vs INTERSECTION - В ЧЕМ РАЗНИЦА?

### INTERSECTION (Пересечение) - НЕ ИСПОЛЬЗУЕТСЯ!

```
TagSearch:       {25, 7}
VectorSearch:    {25, 26}
SemanticSearch: {25}

INTERSECTION = {25, 7} ∩ {25, 26} ∩ {25} = {25}

Плюсы: Высокая точность (все сервисы согласны)
Минусы: Может потерять кандидата если один сервис не нашел
```

### UNION (Объединение) - ИСПОЛЬЗУЕТСЯ!

```
TagSearch:       {25, 7}
VectorSearch:    {25, 26}
SemanticSearch: {25}

UNION = {25, 7, 26}

Плюсы: Не теряем кандидатов, учитываем все мнения
Минусы: Меньше точности, нужна сортировка по confidence
```

### ПРИОРИТЕТЫ (весовой коэффициент):

```
Service  найден:
- 3 сервисами → confidence × 1.8
- 2 сервисами → confidence × 1.4
- 1 сервисом → confidence × 1.0
```

**ПРИМЕР:**
- Service 25: найден 3 сервисами, confidence=0.95 → 0.95 × 1.8 = 1.71 → 1.0
- Service 7: найден 1 сервисом, confidence=0.75 → 0.75 × 1.0 = 0.75

---

## 6. "Нет необходимости уточнять локацию" - ТЕСТИРОВАНИЕ

Нужно запустить тест чтобы найти точную причину!
