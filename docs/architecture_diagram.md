# Архитектура сервисов komunal-dom.ru

## Структура взаимодействия сервисов

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ВНЕШНИЕ ИСТОЧНИКИ                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Telegram Bot  │  Web Chat  │  WhatsApp  │  Test Bot  │  Transcriber      │
└────────┬────────────────┬─────────┬────────────┴────────────┬──────────────┘
         │                │         │                         │
         └────────────────┴─────────┴─────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │ MessageHandlerService │
                    │  (Единая точка входа)  │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
  ┌──────────┐        ┌─────────────┐     ┌──────────────┐
  │   Clean   │        │ DialogMemory│     │ DialogLogger │
  │  Message  │        │   Manager   │     │   Service    │
  └─────┬────┘        └──────┬──────┘     └──────┬───────┘
        │                    │                   │
        └────────────────────┴───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │    MainAgent     │
                    │ (Координатор)    │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
  ┌──────────┐        ┌─────────────┐     ┌──────────────┐
  │  Filter   │        │  Problem    │     │    AIAgent   │
  │Detection │        │Accumulation │     │   Service    │
  │ Service  │        │  Service    │     │  (LLM calls)  │
  └─────┬────┘        └──────┬──────┘     └──────┬───────┘
        │                    │                   │
        └────────────────────┴───────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
  ┌──────────┐        ┌─────────────┐     ┌──────────────┐
  │  Tag      │        │   Vector    │     │  Semantic    │
  │  Search   │        │   Search    │     │   Search     │
  │  Service  │        │   Service   │     │   Service    │
  └──────────┘        └─────────────┘     └──────────────┘
         │                    │                    │
         └────────────────────┴───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Воронка точности │
                    │  (Intersection)  │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   service_detection│
                    │   (БД PostgreSQL) │
                    └───────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                         ЛОГИРОВАНИЕ В БАЗУ ДАННЫХ                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        dialog_logs                                 │  │
│  │  • Все сообщения (inbound/outbound/system)                        │  │
│  │  • LLM запросы и ответы                                             │  │
│  │  • Определение услуг с уверенностью                                 │  │
│  │  • Метаданные, tokens, cost                                         │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                       llm_request_log                               │  │
│  │  • Все запросы к LLM (через AIAgentService)                        │  │
│  │  • provider, model, prompt, response                               │  │
│  │  • tokens, cost, status                                            │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    dialog_memory_store                              │  │
│  │  • Память диалогов (context_json)                                   │  │
│  │  • Адреса, фильтры, история                                         │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Поток сообщения

### 1. Входящее сообщение
```
User → MessageHandlerService
  ├─> DialogLoggerService.log_incoming_message() → dialog_logs
  ├─> MessageCleanerService
  └─> DialogMemoryManager (сохранить в память)
```

### 2. Обработка в MainAgent
```
MessageHandlerService → MainAgent
  ├─> FilterDetectionService (извлечь фильтры через LLM)
  │    └─> AIAgentService.call_llm() → llm_request_log
  ├─> ProblemAccumulationService (накопи информацию)
  │    └─> AIAgentService.call_llm() → llm_request_log
  └─> Воронка точности:
       ├─> TagSearchService
       ├─> VectorSearchService
       ├─> SemanticSearchService
       └─> AIAgentService (уточнение через LLM)
            └─> AIAgentService.call_llm() → llm_request_log
```

### 3. Исходящее сообщение
```
MainAgent → MessageHandlerService
  └─> DialogLoggerService.log_outgoing_message() → dialog_logs
       ├─> message_content (текст ответа)
       ├─> confidence_score (уверенность)
       ├─> service_detected_id (ID услуги)
       └─> metadata (txtPrb, фильтры, etc.)
```

## Критические правила

### 1. Единая точка входа
- ВСЕ сообщения → `MessageHandlerService`
- НИКАКИХ прямых вызовов других сервисов из каналов

### 2. Логирование ОБЯЗАТЕЛЬНО
- ВСЕ сообщения → `dialog_logs` через `DialogLoggerService`
- ВСЕ LLM запросы → `llm_request_log` через `AIAgentService`

### 3. LLM вызовы ТОЛЬКО через AIAgentService
- Запрещены прямые вызовы YandexGPT/OpenAI API
- `AIAgentService.call_llm()` - ЕДИНСТВЕННЫЙ метод
- Автоматическое логирование в `llm_request_log`

### 4. Память диалогов
- `DialogMemoryManager` - управление памятью
- `dialog_memory_store` - хранение в БД
- Автоматическая загрузка/сохранение

## Удаленные/замененные сервисы

### ❌ УДАЛЕНО:
- `message_handler_messagelog` таблица (заменена на `dialog_logs`)
- `MessageLog` Django модель (не используется)
- Прямые вызовы LLM из других сервисов

### ✅ ЗАМЕНЕНО:
- `_log_message()` в `MessageHandlerService` → использует `DialogLoggerService`
- Все логирование → unified в `dialog_logs`

## Метрики и аналитика

### Доступные разрезы в dialog_logs:
- По каналам: `channel`, `direction`
- По времени: `timestamp`
- По пользователям: `user_id`, `django_user_id`
- По диалогам: `dialog_id`, `session_id`
- По услугам: `service_detected_id`, `confidence_score`
- По LLM: `llm_provider`, `llm_model`, `cost_rub`
- По производительности: `processing_time_ms`

### Доступные разрезы в llm_request_log:
- По провайдерам: `provider`, `model`
- По стоимости: `cost_rub`
- По токенам: `total_tokens`
- По времени: `created_at`
- По статусу: `status` (success/error/timeout)
