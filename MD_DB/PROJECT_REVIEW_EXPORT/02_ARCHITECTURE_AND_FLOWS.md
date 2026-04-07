# ARCHITECTURE AND FLOWS - Коммунальный Дом

**Дата:** 2026-03-19

---

## 1. КАК УСТРОЕНА СИСТЕМА

### Высокоуровневая архитектура:

```
┌─────────────────────────────────────────────────────────────┐
│                         КЛИЕНТЫ                             │
├─────────────────────────────────────────────────────────────┤
│  Telegram Bot  │  WhatsApp  │  Веб-чат  │  Внешнее API      │
└────────┬────────┴───────────┴───────────┴─────────┬─────────┘
         │                                            │
         └────────────────────┬───────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Nginx (порт 80)  │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │ Gunicorn (3 workers)│
                    │ Django 6.0         │
                    └─────────┬─────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐   ┌────────▼────────┐   ┌───────▼────────┐
│  Portal App    │   │Message Handler  │   │  LLM Tester    │
│  (заявки,      │   │  (логирование,  │   │  (тестирование)│
│   админка УК)  │   │   веб-чат)      │   │                 │
└───────┬────────┘   └────────┬────────┘   └─────────────────┘
        │                     │
        │           ┌─────────▼─────────┐
        │           │  MainAgent        │
        │           │  (координатор AI) │
        │           └─────────┬─────────┘
        │                     │
        │    ┌────────────────┼────────────────┐
        │    │                │                │
┌───────▼────▼───┐   ┌────────▼────────┐   ┌──▼──────────────┐
│PostgreSQL 16   │   │ AI-сервисы      │   │  Внешние API     │
│services_catalog│   │ (20+ файлов)    │   │  YandexGPT,      │
│dialog_logs     │   │ VectorSearch,   │   │  Embeddings,     │
│ и т.д.         │   │ TagSearch, и    │   │  GigaChat        │
└────────────────┘   │  SemanticSearch │   └──────────────────┘
                     └─────────────────┘
```

---

## 2. ГЛАВНЫЕ ПОТОКИ ДАННЫХ

### Сценарий 1: Обращение жителя через Telegram

```
1. Житель → Telegram: "У меня течет труба в ванной"
   ↓
2. enhanced_aspect_bot.py (Telegram бот)
   ↓
3. message_handler_service.py.handle_incoming_message()
   ↓
4. DialogLoggerService.log_message() → dialog_logs (MessageLog)
   ↓
5. MainAgent.determine_service()
   ├─→ VectorSearchService (векторный поиск по embedding)
   ├─→ TagSearchService (нечеткий поиск по тегам)
   ├─→ SemanticSearchService (логико-семантический поиск)
   └─→ AIAgentService (YandexGPT)
   ↓
6. FilterDetectionService (location, category, incident)
   ↓
7. ProblemAccumulationService (txtPrb - накопление описания)
   ↓
8. MainAgent.generate_response()
   ├─→ Если 1 кандидат: создать заявку
   ├─→ Если несколько: уточняющий вопрос
   └─→ Если нет: запрос уточнения
   ↓
9. DialogLoggerService.log_response() → dialog_logs
   ↓
10. Telegram бот ← Жителю: "Где именно течет?"
```

### Сценарий 2: Создание заявки (SUCCESS)

```
1. Житель → "В ванной на третьем этаже"
   ↓
2. ProblemAccumulationService.accumulate()
   - txtPrb: "у пользователя течет труба в ванной на третьем этаже"
   ↓
3. FilterDetectionService.detect_filters()
   - location: "Индивидуальное" (confidence: 0.9)
   - category: "Водоснабжение" (confidence: 0.85)
   - incident: "Инцидент" (confidence: 0.95)
   ↓
4. MainAgent.check_success_conditions()
   - service_id: 32 ("Прорыв труб в квартире")
   - confidence: 0.87
   - Условия: ✅ location + category + incident известны
   ↓
5. MainAgent.create_request()
   → services_catalog: service_id=32
   → Создать заявку в БД (если есть интеграция)
   ↓
6. Ответ боту: "Заявка создана. Номер: #12345"
```

### Сценарий 3: Веб-чат (через сайт)

```
1. Житель → http://komunal-dom.ru/chat/
   ↓
2. message_handler/views.py.chat_view()
   ↓
3. POST /chat/ (JSON: {"message": "привет"})
   ↓
4. message_handler_service.py.handle_incoming_message()
   ↓ (тот же flow, что и Telegram)
5. JSON Response: {"response": "Здравствуйте! Чем могу помочь?", ...}
```

---

## 3. AI-АРХИТЕКТУРА

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
        │  - service_id=45 (2)  │
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
│(Индивидуальное │  │  │(Инцидент)       │
│ /Общедомовое)  │  │  │ /Запрос)        │
└────────────────┘  │  └─────────────────┘
                   │
             ┌─────▼─────┐
             │category   │
             │(Водоснаб- │
             │ жение и   │
             │ т.д.)     │
             └───────────┘
```

---

## 4. КЛЮЧЕВЫЕ КОМПОНЕНТЫ

### MainAgent (главный координатор)

**Файл:** `main_agent.py`

**Назначение:** Координация всех микросервисов, принятие решения об услуге.

**Ключевые методы:**
- `determine_service()` - определение услуги
- `check_success_conditions()` - проверка условий для создания заявки
- `generate_response()` - генерация ответа пользователю
- `create_request()` - создание заявки

### MessageHandlerService (обработка сообщений)

**Файл:** `message_handler_service.py`

**Назначение:** Единая точка входа для обработки сообщений из всех каналов.

**Ключевые методы:**
- `handle_incoming_message()` - обработка входящего сообщения
- `send_message()` - отправка ответа

### FilterDetectionService (детекция фильтров)

**Файл:** `filter_detection_service.py`

**Назначение:** Определение фильтров (location, category, incident).

**Ключевые методы:**
- `detect_location_type()` - определение локации
- `detect_category()` - определение категории
- `detect_incident_type()` - определение типа инцидента

### ProblemAccumulationService (txtPrb)

**Файл:** `problem_accumulation_service.py`

**Назначение:** Итеративное накопление описания проблемы, предотвращение повторяющихся вопросов.

**Поля txtPrb:**
- `problem` - описание проблемы
- `location` - локация
- `source` - источник проблемы
- `category` - категория
- `severity` - серьезность
- `intensity` - интенсивность
- `object` - объект

---

## 5. БИЗНЕС-ЛОГИКА

### Portal (основное приложение)

**Роли пользователей:**
- `resident` - Житель
- `uk_user` - Пользователь УК
- `direktor_uk` - Директор УК
- `django_admin` - Администратор Django (ИТ)
- `executor` - Исполнитель

**Права доступа:**
- `has_admin_access()` - директор_ук, django_admin
- `is_uk_user()` - uk_user, direktor_uk
- `is_director_uk()` - direktor_uk
- `is_django_admin()` - django_admin

### Message Handler (логирование)

**Каналы связи:**
- `telegram` - Telegram
- `whatsapp` - WhatsApp
- `maxchat` - Мессенджер Макс
- `web` - Веб-сайт
- `test_bot` - Тестовый бот-имитатор
- `transcriber` - Голосовой транскрибатор
- `api` - Внешнее API

**Направления:**
- `inbound` - Входящее (от пользователя)
- `outbound` - Исходящее (от бота)
- `system` - Системное

### LLM Tester (тестирование промптов)

**Типы промптов:**
- `filter_detection` - FilterDetectionService
- `main_agent` - MainAgent
- `problem_accumulation` - ProblemAccumulationService
- `custom` - Кастомный

---

## 6. ВНЕШНИЕ ИНТЕГРАЦИИ

### YandexGPT (AI)

**Файл:** `ai_agent_service.py`

**Назначение:** Генерация текста, классификация, определение услуг.

**API:** YandexGPT API

**Использование:**
- AIAgentService (все вызовы LLM через этот сервис)

### Yandex Embeddings (векторный поиск)

**Файл:** `vector_search_service.py`

**Назначение:** Генерация embedding для услуг и тегов.

**API:** Yandex Embeddings API (`text-search-doc`)

**Размерность:** 256 float

### GigaChat (альтернативный AI)

**Файл:** `gigachat_service.py`

**Назначение:** Альтернативный LLM провайдер.

**Статус:** Неизвестно (используется ли?)

---

## 7. СМЕШЕНИЕ СЛОЕВ

### Проблемные места:

1. **portal/views.py (39KB)** - God Object, нужен рефакторинг
2. **kladr_views.py in portal/** - почему не in kladr/?
3. **ai_manager.py in portal/** - старый AI менеджер? Проверить использование
4. **SemanticPattern (portal)** - дублирует CommunicativeScript (message_handler)?

### Рекомендации:

1. **Разбить portal/views.py на компоненты:**
   - `views/requests.py` - заявки
   - `views/admin.py` - админка УК
   - `views/residents.py` - жители
   - `views/services.py` - услуги

2. **Переместить kladr_views.py → kladr/views.py**

3. **Проверить использование ai_manager.py** - если не используется, удалить

4. **Объединить SemanticPattern и CommunicativeScript** или четко разделить

---

## 8. ПОТОКИ ДАННЫХ В БД

### Основные таблицы:

```
dialog_logs (MessageLog)
├── dialog_id
├── channel (telegram, whatsapp, web, ...)
├── direction (inbound, outbound, system)
├── message_content
├── service_detected_id → services_catalog
├── address_extracted (JSON)
├── metadata (JSON: service_detection, txtPrb, filters)
├── llm_provider, llm_model, tokens_used, cost_rub
└── timestamp

services_catalog (unmanaged)
├── service_id (PK)
├── scenario_name
├── category_id → ref_categories
├── object_id → ref_objects
├── type_id → ref_service_types
├── localization_id → ref_localization
├── embedding_service (JSON: 256 float)
└── tags

communicativescript
├── script_type (fallback, greeting, clarification, ...)
├── channel (telegram, audio, both)
├── text
├── conditions (JSON)
└── priority
```

---

## 9. НЕЯВНЫЕ ЗАВИСИМОСТИ

### Тесные связи:

1. **MainAgent → все микросервисы** (вызывает напрямую)
2. **MessageHandlerService → MainAgent** (единственная точка входа)
3. **DialogLoggerService → MessageLog** (логирует все)
4. **FilterDetectionService → AIAgentService** (LLM вызовы)

### Потенциальные проблемы:

1. **Циклические зависимости?** - Проверить
2. **Hardcoded зависимости** - нет IoC контейнера
3. **Тесная связность** - сложно тестировать

---

## 10. ЧТО НУЖНО УЛУЧШИТЬ

### Критические улучшения:

1. **Разбить portal/views.py** - рефакторинг на компоненты
2. **Создать ai_services/** - модуль для 20+ AI файлов
3. **Внедрить IoC контейнер** - для управления зависимостями

### Средние улучшения:

1. **Унифицировать промпты** - объединить AIPrompt и PromptTemplate
2. **Переместить kladr_views.py → kladr/views.py**
3. **Убрать дублирование** - SemanticPattern vs CommunicativeScript

### Младшие улучшения:

1. **Добавить type hints** - для лучшей документации
2. **Добавить logging** - вместо print
3. **Написать тесты** - для критических компонентов

---

**ВЫВОД:** Система имеет четкую архитектуру с MainAgent как координатором, но страдает от смешения слоев (portal/views.py 39KB) и тесных связей между компонентами. Main improvements: разбить views.py, создать ai_services/, внедрить IoC контейнер.
