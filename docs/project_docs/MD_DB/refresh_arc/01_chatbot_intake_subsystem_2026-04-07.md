# Подсистема: чат-бот приема заявок

Дата актуализации: 2026-04-29

## Что реально работает сейчас

- Чатовый intake больше не использует промежуточный документ `request_intake`.
- После подтверждения создается сразу `work_order` через `work_orders.intake_service.ChatIntakeService.create_from_chat(...)`.
- Диагностический payload intake хранится в `request_mgmt.work_order_event_log.event_payload_json`.
- `AIPrompt` удален из runtime и из SQL-схемы.
- `CommunicativeScript` удален из runtime и из SQL-схемы.
- Production-промпты должны идентифицироваться по `llm_tester.PromptTemplate.slug`.
- `llm_request_log` хранит `caller_service`, `prompt_slug`, `prompt_source`.

## Точки входа

- `/chat/`
- `/chat/api/send/`
- `/chat/api/external/`
- `/chat/api/history/`
- `/chat/api/dialogs-list/`
- `/chat/api/performance-report/`

## Основные runtime-компоненты

- `message_handler_service.py`
- `main_agent.py`
- `ai_agent_service.py`
- `filter_detection_service.py`
- `problem_accumulation_service.py`
- `address_extractor_service.py`
- `work_orders/intake_service.py`
- `trace_report_service.py`

## Адресный pipeline

Источник истины по адресу переходит на новую схему `address`.

### Дом

Хранится в `address.building`:

- `id`
- `fias_guid`
- `street_fias_guid`
- `house_number`
- `full_address`
- `geo_lat`
- `geo_lon`
- `timezone`

### Квартира/помещение

Хранится в `address.unit`:

- `id`
- `building_id`
- `unit_number`
- `fias_guid`

### Логика бота

- FIAS-поиск идет до уровня дома.
- Основной путь: полный адрес.
- Fallback: `street_fias_guid + house_number`.
- Если `street_fias_guid` не найден, дом не считается подтвержденным адресом.
- Квартира не участвует в FIAS-поиске.
- После нахождения дома бот пытается найти локальный объект квартиры по `unit_number`.
- Если квартира найдена, в заявку идет квартирный `service_object`.
- Если квартира не указана или не найдена, это не стоп-фактор: в заявку идет домовой `service_object`.

## Создание заявки

После подтверждения адреса и услуги intake создает:

1. `request_mgmt.work_order`
2. `request_mgmt.work_order_status_history`
3. SLA-структуры нового контура
4. `request_mgmt.work_order_event_log`

Промежуточный `request_intake` в runtime больше не создается.

## Таблицы, которые реально участвуют

### Активные

- `dialog_logs`
- `llm_request_log`
- `message_handler_apierrorlog`
- `services_catalog`
- `ref_categories`
- `ref_service_types`
- `ref_localization`
- `request_mgmt.work_order`
- `request_mgmt.work_order_event_log`
- `request_mgmt.work_order_status_history`
- `request_mgmt.work_order_status_ref`
- `request_mgmt.company_object_service_period`

### Удалены из runtime

- `request_mgmt.request_intake`
- `portal_aiprompt`
- `message_handler_communicativescript`

## Связи с другими подсистемами

### С АДС

- Чат-бот является прямым runtime-входом в `request_mgmt.work_order`.
- Компания определяется не эвристически, а через `service_object + дата -> company_object_service_period`.

### С адресным контуром

- Целевая схема: `address.building`, `address.unit`.
- Старый `kladr` используется только как источник миграции и legacy-слой для перехода.

### С LLM Tester

- Production-промпты агентов и оркестратора должны ссылаться на `PromptTemplate.slug`.

## Что считать устаревшим

- Любые описания с `request_intake` как обязательным runtime-слоем.
- Любые описания `CommunicativeScript` и `AIPrompt` как рабочих справочников.
- Любые описания адреса, где единственным уровнем считается только дом без учета квартирных объектов обслуживания.
