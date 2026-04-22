# INTEGRATIONS_AI_SEARCH - Коммунальный Дом

**Дата:** 2026-03-19

---

## 1. ВНЕШНИЕ СЕРВИСЫ

### YandexGPT (LLM)

**Файл:** `ai_agent_service.py`

**Назначение:** Генерация текста, классификация, определение услуг

**API:** YandexGPT API

**Использование:**
- AIAgentService (все вызовы LLM через этот сервис)
- MainAgent (генерация ответов)
- FilterDetectionService (детекция фильтров)

**Модели:**
- YandexGPT (последняя версия)
- Возможно, другие модели

**Стоимость:** ~0.14 руб для всей БД (350 тегов + 68 услуг) - для embedding

**Логирование:**
- LLMRequestLog (llm_tester) - лог запросов к LLM
- MessageLog.metadata - содержит llm_provider, llm_model, tokens_used, cost_rub

**КРИТИЧНО:** Все вызовы LLM ТОЛЬКО через AIAgentService!

### Yandex Embeddings (векторный поиск)

**Файл:** `vector_search_service.py`

**Назначение:** Генерация embedding для услуг и тегов

**API:** Yandex Embeddings API (`text-search-doc`)

**Размерность:** 256 float

**Использование:**
- VectorSearchService (векторный поиск по embedding)
- Генерация embedding для services_catalog
- Генерация embedding для ref_tags

**Стоимость:** ~0.14 руб для всей БД (350 тегов + 68 услуг)

**Таблицы:**
- services_catalog.embedding_service (JSON: 256 float)
- ref_tags.embedding_tag (JSON: 256 float)

### GigaChat (альтернативный LLM)

**Файл:** `gigachat_service.py`

**Назначение:** Альтернативный LLM провайдер

**API:** GigaChat API

**Статус:** Неизвестно (используется ли?)

**Рекомендация:** Проверить использование, если нет - удалить

---

## 2. AI-АРХИТЕКТУРА

### Воронка точности (система определения услуг):

```
┌──────────────────────────────────────────────────────────┐
│  ВОПРОС: "У меня течет труба в ванной"                  │
└───────────────────┬──────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
┌───────▼────────┐  │  ┌────────▼────────┐
│VectorSearch    │  │  │TagSearch        │
│(embedding)     │  │  │(pg_trgm)        │
│├──────────────┤│  │  ├─────────────────┤
│ services: 3   ││  │  │ services: 5     │
│ conf: 0.82    ││  │  │ conf: 0.75      │
└───────┬────────┘  │  └────────┬────────┘
        │           │           │
        └───────────┼───────────┘
                    │
        ┌───────────▼───────────┐
        │ SemanticSearch        │
        │ (правила, маппинги)   │
        ├───────────────────────┤
        │ services: 2           │
        │ conf: 0.70            │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │ AIAgentService        │
        │ (YandexGPT)           │
        ├───────────────────────┤
        │ services: 1           │
        │ conf: 0.90            │
        └───────────┬───────────┘
                    │
        ┌───────────▼───────────┐
        │ MainAgent (merge)     │
        ├───────────────────────┤
        │ Уникальные: 7 услуг   │
        │ Пересечения:          │
        │  - service_id=32 (3)  │ ← Побеждает!
        └───────────┬───────────┘
                    │
            ┌───────▼────────┐
            │ service_id=32   │
            │ "Прорыв труб в  │
            │  квартире"      │
            └────────────────┘
```

### Детекция фильтров (FilterDetectionService):

```
┌──────────────────────────────────────────────────────────┐
│  txtPrb: "у пользователя течет труба в ванной"          │
└───────────────────┬──────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
┌───────▼────────┐  │  ┌────────▼────────┐
│location_type   │  │  │incident_type    │
│(Индивидуальное │  │  │(Инцидент/Запрос) │
│ /Общедомовое)  │  │  └─────────────────┘
└────────────────┘  │
                   │
             ┌─────▼─────┐
             │category   │
             │(Водоснаб- │
             │ жение и   │
             │ т.д.)     │
             └───────────┘
```

---

## 3. AI-СЕРВИСЫ (20+ ФАЙЛОВ В КОРНЕ)

### Критичные сервисы:

| Сервис | Файл | Назначение | Статус |
|---|---|---|---|
| **MainAgent** | main_agent.py | Главный координатор | ✅ Критично |
| **MessageHandlerService** | message_handler_service.py | Обработка сообщений | ✅ Критично |
| **AIAgentService** | ai_agent_service.py | AI агент (YandexGPT) | ✅ Критично |
| **VectorSearchService** | vector_search_service.py | Векторный поиск | ✅ Критично |
| **TagSearchService** | tag_search_service.py | Поиск по тегам | ✅ Критично |
| **FilterDetectionService** | filter_detection_service.py | Детекция фильтров | ✅ Критично |
| **ProblemAccumulationService** | problem_accumulation_service.py | Накопление txtPrb | ✅ Критично |

### Вспомогательные сервисы:

| Сервис | Файл | Назначение | Статус |
|---|---|---|---|
| **DialogLoggerService** | dialog_logger_service.py | Логирование диалогов | ✅ Важно |
| **SemanticSearchService** | semantic_search_service.py | Семантический поиск | ✅ Важно |
| **CommunicativeScriptsService** | communicative_scripts_service.py | Коммуникативные скрипты | ✅ Важно |

### Диагностика и тестирование:

| Сервис | Файл | Назначение | Статус |
|---|---|---|---|
| **DialogTraceService** | dialog_trace_service.py | Трассировка диалогов | ⚠️ Эксперимент? |
| **TraceReportService** | trace_report_service.py | Отчеты трассировки | ⚠️ Эксперимент? |
| **PerformanceTracer** | performance_tracer.py | Трассировка производительности | ⚠️ Эксперимент? |
| **PerformanceReportService** | performance_report_service.py | Отчеты о производительности | ⚠️ Эксперимент? |
| **TestBotSimulator** | test_bot_simulator.py | Симулятор бота | ✅ Тестирование |

### Интеграции:

| Сервис | Файл | Назначение | Статус |
|---|---|---|---|
| **AddressExtractorService** | address_extractor_service.py | Извлечение адресов | ✅ Используется |
| **MessageCleanerService** | message_cleaner_service.py | Очистка сообщений | ❓ Неизвестно |
| **GigaChatService** | gigachat_service.py | GigaChat API | ❓ Неизвестно |

### Боты:

| Сервис | Файл | Назначение | Статус |
|---|---|---|---|
| **EnhancedAspectBot** | enhanced_aspect_bot.py | Telegram бот | ✅ Критично |

### Утилиты:

| Сервис | Файл | Назначение | Статус |
|---|---|---|---|
| **CreateFilterPrompts** | create_filter_prompts.py | Создание фильтр промптов | ⚠️ Временный? |

---

## 4. ВЕКТОРНЫЙ ПОИСК (VectorSearchService)

### Реализация:

**Файл:** `vector_search_service.py`

**Двойной векторный поиск:**

1. **По embedding тегов** (точность):
   - Загружает embedding из `ref_tags.embedding_tag` (JSONB, 256 float)
   - Вычисляет косинусное сходство
   - Порог: 0.70
   - Группирует по service_id (максимум)

2. **По embedding услуг** (полнота):
   - Загружает embedding из `services_catalog.embedding_service` (JSONB, 256 float)
   - Вычисляет косинусное сходство
   - Порог: 0.70

3. **Слияние результатов:**
   - Средневзвешенное: `0.6 * tag_conf + 0.4 * service_conf`
   - Если найден только в одном → не штрафуем
   - Сортировка по DESC, возврат TOP-10

**Формула косинусного сходства:**
```
cosine_sim = (vec1 · vec2) / (||vec1|| * ||vec2||)
```

**Генерация embedding:**
- Скрипты: `generate_tag_embeddings.py`, `generate_service_embeddings.py`
- Модель: Yandex Embeddings API (`text-search-doc`)
- Размерность: 256 float
- Предобработка: NLTK stopwords (151 слово) + pymorphy2 лемматизация

**Стоимость:** ~0.14 руб для всей БД (350 тегов + 68 услуг)

---

## 5. ПОИСК ПО ТЕГАМ (TagSearchService)

### Реализация:

**Файл:** `tag_search_service.py`

**Технологии:**
- pg_trgm (триграммный индекс в PostgreSQL)
- pymorphy2 (морфология русского языка)
- rapidfuzz (нечеткое сравнение строк)

**Алгоритм:**
1. Поиск по тегам (pg_trgm)
2. Лемматизация (pymorphy2)
3. Нечеткое сравнение (rapidfuzz)
4. Фильтрация по порогу (0.70)
5. Группировка по service_id

**Индексы:**
- `service_tags` - связь услуг и тегов
- `ref_tags.tag_name` - триграммный индекс

---

## 6. СЕМАНТИЧЕСКИЙ ПОИСК (SemanticSearchService)

### Реализация:

**Файл:** `semantic_search_service.py`

**Назначение:** Логико-семантический поиск

**Алгоритм:**
- Правила и маппинги
- Ключевые слова
- Семантические паттерны

**Статус:** Требует документации

---

## 7. DETECTION ФИЛЬТРОВ (FilterDetectionService)

### Реализация:

**Файл:** `filter_detection_service.py`

**Назначение:** Определение фильтров (location, category, incident)

**Фильтры:**
- **location_type:** Индивидуальное / Общедомовое
- **category:** Водоснабжение, Отопление, Электричество, и т.д.
- **incident_type:** Инцидент / Запрос

**Алгоритм:**
1. Извлечение сущностей из txtPrb
2. Классификация по правилам
3. Вызов LLM для неочевидных случаев
4. Вычисление confidence

**Использует:** AIAgentService (LLM вызовы)

---

## 8. НАКОПЛЕНИЕ ОПИСАНИЯ (ProblemAccumulationService)

### Реализация:

**Файл:** `problem_accumulation_service.py`

**Назначение:** Итеративное накопление информации из диалога

**Принцип:**
- "привет" → '' (нет информации)
- "у меня течет" → 'у пользователя течет'
- "В зале" → 'у пользователя течет в зале'
- "Батарея" → 'у пользователя течет из батареи (отопление) в зале'

**Поля txtPrb:**
- `problem` - описание проблемы
- `location` - локация
- `source` - источник проблемы
- `category` - категория
- `severity` - серьезность
- `intensity` - интенсивность
- `object` - объект

**КРИТИЧЕСКИ ВАЖНО:** НЕ спрашивай то, что УЖЕ известно!

---

## 9. ДИАГНОСТИКА И ТРАССИРОВКА

### DialogTraceService:

**Файл:** `dialog_trace_service.py`

**Назначение:** Трассировка диалогов для диагностики

**Показывает:**
- Результаты микросервисов (TagSearch, VectorSearch, SemanticSearch, AI)
- LLM промты
- Установленные фильтры (location, category, incident)
- Память диалога (DialogMemoryManager)

**Запуск:**
```bash
python dialog_trace_service.py --session-id web_123_abc
python dialog_trace_service.py --telegram-user-id 123456789
```

### TraceReportService:

**Файл:** `trace_report_service.py`

**Назначение:** Генерация подробных отчетов

**Запуск:**
```python
from trace_report_service import generate_dialog_trace
path = await generate_dialog_trace('telegram_123456')
```

**Выход:** Файл `/tmp/_tras_diag_ГГГГММДД_ЧЧММСС.md`

---

## 10. ЭКСПЕРИМЕНТАЛЬНЫЕ / ПОДОЗРИТЕЛЬНЫЕ ЧАСТИ

### Вероятно, экспериментальные:

1. **DialogTraceService** - для диагностики, возможно, временный
2. **TraceReportService** - для отчетов, возможно, временный
3. **PerformanceTracer** - для производительности, возможно, временный
4. **PerformanceReportService** - для отчетов, возможно, временный
5. **GigaChatService** - альтернативный LLM, используется ли?

### Требуют проверки:

1. **MessageCleanerService** - очистка сообщений, используется ли?
2. **CreateFilterPrompts** - создание промптов, временный скрипт?

### Рекомендация:

- Проверить использование экспериментальных сервисов
- Если не используются - удалить или переместить в `experimental/`
- Если временные скрипты - переместить в `scripts/`

---

## 11. ЧТО ЯВЛЯЕТСЯ ОБЯЗАТЕЛЬНЫМ

### Критичные компоненты (без них система не работает):

1. **MainAgent** - главный координатор
2. **MessageHandlerService** - обработка сообщений
3. **AIAgentService** - AI агент
4. **VectorSearchService** - векторный поиск
5. **TagSearchService** - поиск по тегам
6. **FilterDetectionService** - детекция фильтров
7. **ProblemAccumulationService** - накопление txtPrb
8. **EnhancedAspectBot** - Telegram бот

### Важные компоненты:

1. **DialogLoggerService** - логирование
2. **SemanticSearchService** - семантический поиск
3. **CommunicativeScriptsService** - коммуникативные скрипты
4. **AddressExtractorService** - извлечение адресов

### Опциональные компоненты:

1. **DialogTraceService** - диагностика
2. **TraceReportService** - отчеты
3. **PerformanceTracer** - производительность
4. **PerformanceReportService** - отчеты о производительности
5. **TestBotSimulator** - тестирование

---

## 12. ЧТО ПОХОЖЕ НА ЭКСПЕРИМЕНТ / РУДИМЕНТ

### Вероятно, экспериментальное:

1. **GigaChatService** - альтернативный LLM (неизвестно, используется ли)
2. **MessageCleanerService** - очистка сообщений (неизвестно, используется ли)
3. **CreateFilterPrompts** - создание промптов (временный скрипт?)

### Рекомендация:

- Проверить использование `grep -r "GigaChat" /var/www/komunal-dom_ru/`
- Проверить использование `grep -r "MessageCleaner" /var/www/komunal-dom_ru/`
- Если не используются - удалить или переместить в `experimental/`

---

## 13. ХАКИЕ ЧАСТИ ВЫГЛЯДЯТ ХРУПКИМИ

### Тесные связи:

1. **MainAgent → все микросервисы** (вызывает напрямую)
   - **Проблема:** Сложно тестировать
   - **Решение:** Внедрить IoC контейнер

2. **AIAgentService → YandexGPT API** (прямые HTTP запросы)
   - **Проблема:** Нет изоляции
   - **Решение:** Создать адаптер

### Hardcoded зависимости:

1. **Нет IoC контейнера** - все зависимости создаются напрямую
2. **Нет интерфейсов** - нет абстракций
3. **Нет mocking** - сложно тестировать

### Потенциальные точки отказа:

1. **YandexGPT API** - если недоступен, AI не работает
2. **Yandex Embeddings API** - если недоступен, векторный поиск не работает
3. **PostgreSQL** - если недоступен, система не работает

---

## 14. РЕКОМЕНДАЦИИ

### Минимальные улучшения:

1. **Проверить использование экспериментальных сервисов**
2. **Удалить неиспользуемые** (GigaChatService, MessageCleanerService)
3. **Переместить временные скрипты** в `scripts/`

### Средние улучшения:

1. **Создать ai_services/** - модуль для 20+ AI файлов
2. **Внедрить IoC контейнер** - для управления зависимостями
3. **Добавить адаптеры** - для внешних API

### Сложные улучшения:

1. **Рефакторинг MainAgent** - разбить на компоненты
2. **Добавить интерфейсы** - для тестируемости
3. **Добавить mocking** - для юнит-тестов

---

**ВЫВОД:** Система имеет мощную AI-архитектуру (воронка точности с 4 микросервисами), но страдает от отсутствия модульности (20+ сервисов в корне) и тесных связей между компонентами. Главные проблемы: нет IoC контейнера, сложно тестировать, экспериментальные сервисы не отделены от боевых. Quick wins: проверить использование экспериментальных сервисов, создать ai_services/, внедрить базовый IoC.
