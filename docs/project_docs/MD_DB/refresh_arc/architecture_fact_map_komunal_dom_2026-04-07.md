# Фактическая карта подсистем komunal-dom.ru

Дата: 2026-04-07

Принцип:
- ниже только то, что подтверждено кодом, URL, процессами или SQL;
- материалы из `MD_DB` не считаются источником истины без подтверждения;
- это рабочий документ для будущего рефакторинга и разведения таблиц по схемам.

## 1. Portal / кабинеты / роли

Назначение:
- входная оболочка сайта;
- личные кабинеты;
- роль-зависимая навигация;
- административные экраны портала.

Точки входа:
- `/`
- `/welcome/`
- `/subscribers/`
- `/chief-engineer/`
- `/director/`
- `/admin-uk/`
- `/regulatory-chat/`
- `/executor/` и legacy API вокруг исполнителя

Ключевые файлы:
- `komunal_dom/urls.py`
- `portal/urls.py`
- `portal/views.py`
- `portal/admin_views.py`
- `portal/models.py`

Таблицы:
- `portal_userprofile`
- `nsi_company`
- `request_mgmt.user_company_membership`
- `request_mgmt.company_department`
- в части кабинета жителя: `request_mgmt.work_order`

Пруфы:
- `komunal_dom/urls.py` подключает `path('', include('portal.urls'))`
- `portal/urls.py` содержит маршруты landing, кабинеты, `regulatory-chat`, `admin-uk`, legacy `/executor/`
- `portal/views.py` использует `UserProfile`, `Company`, `get_primary_membership`, `WorkOrder`

Статус:
- `CORE`

## 2. Нормативный консультант

Назначение:
- UI для поиска по нормативным документам ЖКХ;
- не является Django-chat backend внутри основного проекта.

Точки входа:
- `/regulatory-chat/`

Реальный runtime:
- UI рендерится из `portal`
- фронтенд отправляет POST на `http://komunal-dom.ru:8002/search`
- `nginx :8002` проксирует на `127.0.0.1:8001`
- backend живет вне проекта: `/home/olga/normativ_docs/Волков/vector-db-test/backend/main_cpu.py`

Ключевые файлы:
- `portal/views.py`
- `portal/templates/portal/normative_chat.html`
- `static/js/normative-chat.js`
- `/etc/nginx/sites-enabled/normativ-api.conf`
- `/home/olga/normativ_docs/Волков/vector-db-test/backend/main_cpu.py`

Таблицы основного Django-проекта:
- на текущем шаге прямое использование таблиц проекта **не подтверждено**

Пруфы:
- `portal/urls.py`: `path('regulatory-chat/', views.regulatory_chat, ...)`
- `portal/views.py`: `def regulatory_chat(...) -> render(... 'portal/normative_chat.html' ...)`
- `static/js/normative-chat.js`: `fetch('http://komunal-dom.ru:8002/search', ...)`
- `/etc/nginx/sites-enabled/normativ-api.conf`: `proxy_pass http://127.0.0.1:8001/;`
- `ss -ltnp` показывает listener на `:8001`
- `ps -ef` показывает `python3 main_cpu.py` из внешнего каталога
- `main_cpu.py` поднимает `FastAPI`, использует `FAISS`, `SentenceTransformer`, Yandex API

Статус:
- `CORE`, но `EXTERNAL` относительно Django-проекта

## 3. AI чатбот приема заявок

Назначение:
- web-chat для общения с пользователем;
- AI-классификация и обработка сообщений;
- логирование диалогов и LLM-вызовов.

Точки входа:
- `/chat/`
- `/chat/api/send/`
- `/chat/api/external/`
- `/chat/api/history/`
- `/chat/api/dialogs-list/`
- `/chat/api/performance-report/`

Ключевые компоненты:
- Django app `message_handler`
- `message_handler_service.py`
- `main_agent.py`
- `ai_agent_service.py`
- `filter_detection_service.py`
- `semantic_search_service.py`
- `vector_search_service.py`
- `tag_search_service.py`

Таблицы:
- `dialog_logs`
- `message_handler_communicativescript`
- `message_handler_apierrorlog`
- `llm_request_log`
- `services_catalog`
- `ref_categories`
- `ref_service_types`
- `ref_localization`

Что важно:
- на текущем шаге не подтверждено создание `request_intake`
- на текущем шаге не подтверждено создание `work_order`
- на текущем шаге не найдено живых ссылок на `ai_models`, `ai_providers`, `ai_model_pricing`, `ai_request_history`, `ai_type_of_service`

Пруфы:
- `komunal_dom/urls.py`: `path('chat/', include('message_handler.urls'))`
- `message_handler/urls.py`: маршрут `'' -> web_chat`, API send/history/dialogs-list/performance-report`
- `message_handler/views.py`: `send_message()` создает `MainAgent`, `MessageHandlerService`, вызывает `handle_incoming_message(...)`
- `message_handler/models.py`: `MessageLog` использует `db_table = 'dialog_logs'`
- `ai_agent_service.py`: есть `INSERT INTO llm_request_log`
- `trace_report_service.py`: есть `FROM llm_request_log`
- `main_agent.py`, `filter_detection_service.py`, `semantic_search_service.py`, `message_handler/admin.py` читают `services_catalog` и `ref_*`
- поиск по текущему коду не нашел рабочих ссылок на `request_intake` вне моделей/admin/demo seed
- поиск по текущему коду не нашел `WorkOrder.objects.create` вне demo-команды

Статус:
- `CORE`

## 4. LLM Tester

Назначение:
- тестирование промптов;
- хранение шаблонов, пресетов и результатов тестов;
- инженерный инструмент вокруг AI-слоя.

Точки входа:
- `/llm-tester/`
- `/llm-tester/prompts/`
- `/llm-tester/test/<slug>/`
- `/llm-tester/results/`
- API внутри `/llm-tester/api/...`

Ключевые файлы:
- `llm_tester/urls.py`
- `llm_tester/models.py`
- `llm_tester/views.py`

Таблицы:
- `llm_tester_prompttemplate`
- `llm_tester_promptpreset`
- `llm_tester_llmtestresult`

Пруфы:
- `komunal_dom/urls.py`: `path('llm-tester/', include('llm_tester.urls'))`
- `llm_tester/urls.py` описывает dashboard, prompts, test, results и API
- `llm_tester/models.py` задает `db_table = 'llm_tester_prompttemplate'`, `llm_tester_promptpreset`, `llm_tester_llmtestresult`
- в текущем коде не подтверждено использование старых таблиц `prompt_templates` и `prompt_template_versions`

Статус:
- `SUPPORT`

## 5. Диалоговая трассировка и отчеты

Назначение:
- диагностика AI-диалогов;
- просмотр сессий;
- генерация trace/report файлов.

Точки входа:
- `/admin-uk/dialog-trace/`
- `/api/dialog-trace/`
- `/api/dialog-sessions/`
- `/api/dialog-reports/`
- `/api/dialog-full-trace/`

Ключевые файлы:
- `portal/views.py`
- `dialog_trace_service.py`
- `trace_report_service.py`

Таблицы:
- `dialog_logs`
- `llm_request_log`

Опционально/исторически:
- `debug_trace_log`
- `debug_span_log`

Пруфы:
- `portal/urls.py` публикует все trace endpoints
- `portal/views.py` читает `dialog_logs` в `dialog_trace_api` и `api_dialog_sessions`
- `portal/views.py` вызывает `TraceReportService`
- `trace_report_service.py` читает `llm_request_log`
- в текущем коде живых вставок в `debug_trace_log` и `debug_span_log` не подтверждено

Статус:
- `SUPPORT`

## 6. Новая система управления заявками

Назначение:
- основной новый контур заявок ЖКХ;
- исполнители, подрядчики, менеджмент, жители;
- статусы, SLA, маршруты, история.

Точки входа:
- `/work_orders/...`

Ключевые файлы:
- `work_orders/urls.py`
- `work_orders/views.py`
- `work_orders/models.py`
- `work_orders/templates/work_orders/*`

Таблицы:
- `request_mgmt.work_order`
- `request_mgmt.work_order_status_history`
- `request_mgmt.work_order_status_ref`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.user_company_membership`
- `request_mgmt.company_department`
- `request_mgmt.company_route_mapping`
- `request_mgmt.contractor_organization`
- `request_mgmt.route_ref`
- `request_mgmt.sla_policy`

Дополнительные, но пока пустые:
- `request_mgmt.request_intake`
- `request_mgmt.sla_instance`
- `request_mgmt.work_order_event_log`
- `request_mgmt.work_order_attachment`
- `request_mgmt.notification_outbox`
- `request_mgmt.company_object_service_period`

Пруфы:
- `komunal_dom/settings.py`: app `work_orders.apps.WorkOrdersConfig`
- `komunal_dom/urls.py`: `path('work_orders/', include('work_orders.urls'))`
- `work_orders/views.py` массово использует `WorkOrder.objects.filter(...)`
- `work_orders/models.py` задает `db_table` в схеме `request_mgmt`
- в БД есть реальные записи в `work_order`, `work_order_status_history`, `sla_policy`, `user_company_membership`

Статус:
- `CORE`

## 7. Legacy-контур заявок исполнителя

Назначение:
- старый маршрут исполнителя, который частично совместим с новым контуром, но все еще работает поверх старой таблицы.

Точки входа:
- `/executor/`
- `/executor/take/<id>/`
- `/executor/arrived/<id>/`
- `/executor/complete/<id>/`
- `/executor/upload-photo/<id>/`
- `/executor/report/<id>/`

Ключевые файлы:
- `portal/urls.py`
- `portal/views.py`

Таблицы:
- `bot_service_requests`
- `auth_user` через joins для отчета

Пруфы:
- `portal/urls.py` публикует `/executor/...`
- `portal/views.py` делает `SELECT` и `UPDATE` по `bot_service_requests`
- `portal/views.py` в `executor_report` сначала пытается открыть новый `WorkOrder`, но потом падает обратно на legacy SQL

Статус:
- `LEGACY`

## 8. SQL интерфейс БД

Назначение:
- read-only просмотр таблиц, структуры, данных и связей БД через веб.

Точки входа:
- `/db-sql/`
- `/db-sql/structure/`
- `/db-sql/data/`
- `/db-sql/relations/`

Ключевые файлы:
- `database_viewer/urls.py`
- `database_viewer/views.py`
- `database_viewer/templates/database_viewer/*`

Особенность:
- описания таблиц берутся из PostgreSQL comments через `obj_description(...)`

Пруфы:
- `komunal_dom/urls.py`: `path('db-sql/', include('database_viewer.urls'))`
- `database_viewer/views.py` в `table_list()` делает `obj_description((schema||'.'||table)::regclass, 'pg_class')`

Статус:
- `SUPPORT`

## Факты по спорным AI-таблицам

### Реально подтверждено как используемое

- `llm_request_log`
- `dialog_logs`
- `llm_tester_prompttemplate`
- `llm_tester_promptpreset`
- `llm_tester_llmtestresult`
- `services_catalog`
- `ref_categories`
- `ref_service_types`
- `ref_localization`

Пруфы:
- прямые `INSERT INTO llm_request_log` в `ai_agent_service.py`
- прямые `FROM llm_request_log` в `trace_report_service.py`
- ORM `MessageLog -> dialog_logs` в `message_handler/models.py`
- ORM `llm_tester_*` в `llm_tester/models.py`
- прямые чтения `services_catalog` и `ref_*` в `main_agent.py`, `filter_detection_service.py`, `semantic_search_service.py`, `message_handler/admin.py`

### Не подтверждено как используемое текущим кодом

- `ai_cost_tracking`
- `ai_model_pricing`
- `ai_models`
- `ai_providers`
- `ai_request_history`
- `ai_type_of_service`
- `prompt_templates`
- `prompt_template_versions`
- `llm_response_cache`

Пруфы:
- поиск по текущему коду проекта не дал живых ссылок на эти таблицы;
- найденные попадания были либо в `old/`, backup-деревьях, SQL-черновиках, либо в свежем файле с комментариями;
- для `llm_response_cache` текущих чтений/записей не найдено.

Ограничение:
- отсутствие ссылки в текущем коде не равно автоматическому решению на удаление;
- эти таблицы остаются в статусе `UNDER_REVIEW`, пока не завершено полное архитектурное описание и план рефакторинга.

## Предварительная декомпозиция по подсистемам

1. `portal` как оболочка, роли, кабинеты и маршрутизация UI.
2. `message_handler + main_agent + AI/search services` как ядро AI чатбота приема заявок.
3. `llm_tester` как инженерный контур промптов и тестирования.
4. `dialog trace/reporting` как диагностический контур над `dialog_logs` и `llm_request_log`.
5. `work_orders` как новый доменный контур управления заявками.
6. `legacy executor / bot_service_requests` как временно сохраненный старый контур.
7. `database_viewer` как админский SQL-интерфейс.
8. `regulatory-chat` как внешняя нормативная подсистема с отдельным backend.

