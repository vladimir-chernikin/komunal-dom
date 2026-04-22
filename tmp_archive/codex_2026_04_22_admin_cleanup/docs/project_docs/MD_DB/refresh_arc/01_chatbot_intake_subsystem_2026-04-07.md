# Подсистема: Чат-Бот приема заявок

Дата: 2026-04-07

## Обновление 2026-04-13

- В runtime добавлен адресный gate перед классификацией услуги: чат сначала вытягивает адрес, валидирует его по ФИАС и только потом продолжает intake.
- Для intake введен промежуточный нормализованный JSON, который сохраняется в `request_intake.normalized_payload_json`.
- После подтверждения услуги чат теперь реально создает `request_intake` и `work_order`, а не останавливается на `CONFIRMED`.
- Источник создания заявки для чата: `creation_source='bot_json'`.
- Building-level адрес уже достаточен для создания заявки. Привязка квартир к ФИАС отложена.
- Ограничение текущей версии: определение `company` для чатовой заявки пока эвристическое, потому что в данных нет полноценной прямой связки `service_object -> company`.

## Назначение

Подсистема принимает сообщения пользователя через web/API-каналы, прогоняет их через AI-обработку, классификацию, поиск услуг и логирование.

На текущем шаге это:
- AI-чат;
- классификация и маршрутизация на уровне понимания текста;
- логирование сообщений и LLM-вызовов;
- прямое создание `request_intake` / `work_order` после подтверждения.

## Точки входа

- `/chat/`
- `/chat/api/send/`
- `/chat/api/external/`
- `/chat/api/history/`
- `/chat/api/dialogs-list/`
- `/chat/api/performance-report/`

## Основные компоненты

### Django app

- `message_handler`

### Оркестрация и обработка

- `message_handler_service.py`
- `main_agent.py`
- `ai_agent_service.py`
- `message_cleaner_service.py`
- `filter_detection_service.py`
- `semantic_search_service.py`
- `vector_search_service.py`
- `tag_search_service.py`
- `address_extractor_service.py`
- `communicative_scripts_service.py`

### Связанные служебные компоненты

- `dialog_logger_service.py`
- `trace_report_service.py`
- `dialog_trace_service.py`

## Реальный поток обработки

1. Пользователь открывает `/chat/`.
2. `message_handler.views.web_chat()` рендерит web-чат.
3. `message_handler.views.send_message()` принимает AJAX POST.
4. Создается `MainAgent`.
5. Создается `MessageHandlerService`.
6. `MessageHandlerService.handle_incoming_message(...)`:
   - логирует входящее сообщение;
   - подтягивает историю диалога;
   - чистит текст;
   - вызывает `MainAgent.process_service_detection(...)`.
7. Параллельно и/или последовательно используются сервисы поиска и AI.
8. Ответ уходит обратно в web-chat.
9. Если адрес подтвержден и услуга определена, формируется промежуточный intake JSON.
10. После подтверждения пользователя создаются `request_intake`, `work_order`, `work_order_status_history`, SLA-строки и event log.
11. Дополнительно может быть сгенерирован trace-report.

## Что реально подтверждено кодом

### Маршруты

Пруфы:
- [komunal_dom/urls.py](/var/www/komunal-dom_ru/komunal_dom/urls.py)
- [message_handler/urls.py](/var/www/komunal-dom_ru/message_handler/urls.py)

Факт:
- `/chat/` подключен как отдельный Django app `message_handler`.

### Web chat и send API

Пруфы:
- [message_handler/views.py](/var/www/komunal-dom_ru/message_handler/views.py)

Факты:
- `web_chat()` рендерит шаблон web-чата;
- `send_message()` создает `MainAgent` и `MessageHandlerService`;
- `send_message()` вызывает `handle_incoming_message(...)`.

### Лог сообщений

Пруфы:
- [message_handler/models.py](/var/www/komunal-dom_ru/message_handler/models.py)

Факты:
- ORM-модель `MessageLog`;
- `db_table = 'dialog_logs'`;
- именно `dialog_logs` является текущим живым журналом сообщений.

### Лог LLM-вызовов

Пруфы:
- [ai_agent_service.py](/var/www/komunal-dom_ru/ai_agent_service.py)
- [trace_report_service.py](/var/www/komunal-dom_ru/trace_report_service.py)

Факты:
- в `ai_agent_service.py` есть `INSERT INTO llm_request_log`;
- в `trace_report_service.py` есть чтение из `llm_request_log`;
- таблица `llm_request_log` живая.

### Справочники услуг и классификация

Пруфы:
- [main_agent.py](/var/www/komunal-dom_ru/main_agent.py)
- [filter_detection_service.py](/var/www/komunal-dom_ru/filter_detection_service.py)
- [semantic_search_service.py](/var/www/komunal-dom_ru/semantic_search_service.py)
- [message_handler/admin.py](/var/www/komunal-dom_ru/message_handler/admin.py)

Факты:
- текущий AI-слой реально читает `services_catalog`;
- реально читает `ref_categories`, `ref_service_types`, `ref_localization`.

## Таблицы, которые реально участвуют

### Подтверждено как живое

- `dialog_logs`
- `llm_request_log`
- `message_handler_communicativescript`
- `message_handler_apierrorlog`
- `services_catalog`
- `ref_categories`
- `ref_service_types`
- `ref_localization`

### Под вопросом, но не подтверждено как живое

- `ai_cost_tracking`
- `ai_model_pricing`
- `ai_models`
- `ai_providers`
- `ai_request_history`
- `ai_type_of_service`
- `llm_response_cache`

Факт:
- по текущему коду прямых живых ссылок на этот набор не найдено;
- решение по ним отложено.

## Что НЕ подтверждено на текущем шаге

### Создание нового контура заявок

Пруфы:
- `work_orders/intake_service.py`
- `message_handler_service.py`

Вывод:
- чат-бот создает `request_mgmt.request_intake`;
- чат-бот создает `request_mgmt.work_order`;
- creation pipeline отделен от LLM-классификации через промежуточный JSON payload.

Это важно:
- чат-бот и АДС теперь связаны через runtime, но часть организационных правил пока замкнута на эвристики маршрутизации и выбора компании.

## Пересечения с другими подсистемами

### С АДС

- использует тот же каталог услуг;
- потенциально должен стать входом в `request_intake`, но пока этого нет.

### С Portal

- использует пользовательские профили и общую сессию пользователя;
- UI чат открыт через основной Django-проект.

### С LLM Tester

- использует тот же слой LLM и часть общей prompt/AI-логики, но хранение тестовых сущностей идет в `llm_tester_*`.

### С трассировкой

- `dialog_logs` и `llm_request_log` питают `/admin-uk/dialog-trace/`.

## Legacy и риски

- AI-таблицы старой модели до конца не размечены;
- новый контур заявок в чат еще не встроен;
- часть диагностики и AI-логики лежит в корне проекта, а не внутри явной bounded context структуры.

## Предварительная целевая ответственность подсистемы

Подсистема "Чат-Бот приема заявок" в будущем должна отвечать только за:
- прием сообщения;
- AI-понимание;
- накопление контекста;
- определение intent/услуги/адреса/критичности;
- создание канонического `request_intake`.

Она не должна напрямую нести на себе:
- жизненный цикл исполнения заявки;
- SLA;
- статусы АДС;
- управленческие дашборды исполнителей.
