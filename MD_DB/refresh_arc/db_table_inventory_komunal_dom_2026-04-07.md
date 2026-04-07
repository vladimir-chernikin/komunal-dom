# Инвентаризация таблиц БД `aspect_objects_db`

Дата: 2026-04-07

Источник проверки:
- SSH на `root@155.212.217.73`
- проект: `/var/www/komunal-dom_ru`
- БД: PostgreSQL `aspect_objects_db`
- основной новый контур заявок: Django app `work_orders`
- старый контур заявок: `portal/views.py` через raw SQL к `bot_service_requests`

## Ключевой вывод

Сейчас в проекте одновременно живут два контура заявок:

1. Новый контур: `request_mgmt.work_order` и связанные таблицы `work_orders`.
2. Старый контур: `public.bot_service_requests`, который все еще используется в `portal/views.py` для кабинета исполнителя.

То есть `bot_service_requests` пока нельзя считать безопасным кандидатом на удаление, несмотря на то что стратегически основная модель уже перенесена в `work_order`.

Дополнительно подтверждено:

3. Нормативный консультант `/regulatory-chat/` не работает на Django-таблицах этого проекта напрямую.
Его UI живет в `portal`, но поиск уходит на отдельный backend: `nginx :8002 -> python3 main_cpu.py :8001` из внешнего каталога `/home/olga/normativ_docs/Волков/vector-db-test/backend`.

4. По AI-таблицам `ai_*` прежний вывод "кандидаты на удаление" отозван.
На текущем шаге они классифицируются как **требующие дополнительной архитектурной проверки**, даже несмотря на отсутствие прямых ссылок в текущем коде проекта.

## Статусы

- `ACTIVE` - таблица реально используется текущим кодом или обязательна для работающего контура.
- `ACTIVE_LEGACY` - старый, но до сих пор работающий контур.
- `DORMANT` - модель/маршрут/архитектура есть, но данных сейчас нет.
- `ARCHIVE` - резервная или историческая копия.
- `SYSTEM` - системные таблицы Django/PostgreSQL-приложения.
- `CANDIDATE_REMOVE` - явный кандидат на удаление после короткой контрольной проверки.
- `UNDER_REVIEW` - по таблице нет явных живых ссылок в текущем коде, но окончательное решение отложено до завершения архитектурного описания подсистем.

## Полная инвентаризация

| Таблица | Записей | Статус | Русское описание |
|---|---:|---|---|
| `public.ai_cost_tracking` | 0 | `UNDER_REVIEW` | Историческая таблица учета стоимости AI-вызовов. В текущем коде живых ссылок не найдено, но решение о судьбе отложено до полного описания AI-подсистем. |
| `public.ai_model_pricing` | 0 | `UNDER_REVIEW` | Исторический справочник цен AI-моделей. Прямых ссылок в текущем коде не найдено, но удаление пока не рассматривается. |
| `public.ai_models` | 0 | `UNDER_REVIEW` | Исторический справочник AI-моделей. Нуждается в дополнительной проверке после полного картирования AI-архитектуры. |
| `public.ai_providers` | 0 | `UNDER_REVIEW` | Исторический справочник AI-провайдеров. Окончательная классификация отложена до завершения архитектурного анализа. |
| `public.ai_request_history` | 0 | `UNDER_REVIEW` | Историческая таблица AI-запросов. Текущий проект живо использует `llm_request_log`, но связь со старыми подсистемами еще проверяется. |
| `public.ai_type_of_service` | 0 | `UNDER_REVIEW` | Исторический справочник типов услуг для старой AI-классификации. Решение по нему откладывается до полного пересмотра AI-слоя. |
| `public.auth_group` | 0 | `SYSTEM` | Системная таблица Django групп пользователей. |
| `public.auth_group_permissions` | 0 | `SYSTEM` | Связка групп и прав Django. |
| `public.auth_permission` | 200 | `SYSTEM` | Системный справочник прав Django. |
| `public.auth_user` | 14 | `ACTIVE` | Основная таблица пользователей Django. Используется по всему проекту и в новом контуре заявок. |
| `public.auth_user_groups` | 0 | `SYSTEM` | Связка пользователей и групп Django. |
| `public.auth_user_user_permissions` | 0 | `SYSTEM` | Индивидуальные права пользователей Django. |
| `public.bot_service_requests` | 4 | `ACTIVE_LEGACY` | Старая таблица заявок исполнителя. До сих пор используется в `portal/views.py` для взятия заявки, прибытия, завершения, фото и печатного отчета. |
| `public.bot_service_requests_backup` | 4 | `ARCHIVE` | Резервная копия старой таблицы заявок. Рабочих обращений из текущего кода не найдено. |
| `public.debug_span_log` | 0 | `CANDIDATE_REMOVE` | Пустая отладочная таблица трассировки. Живого использования в текущем коде не найдено. |
| `public.debug_trace_log` | 0 | `CANDIDATE_REMOVE` | Старая отладочная трассировка AI/диалогов. В текущем коде остались только SQL-скрипты сопровождения. |
| `public.dialog_logs` | 6526 | `ACTIVE` | Основной журнал входящих и исходящих сообщений пользователей и бота. ORM-модель `message_handler.MessageLog`. |
| `public.django_admin_log` | 125 | `SYSTEM` | Журнал действий в Django admin. |
| `public.django_content_type` | 32 | `SYSTEM` | Системная таблица типов моделей Django. |
| `public.django_migrations` | 66 | `SYSTEM` | История примененных миграций Django. |
| `public.django_session` | 123 | `SYSTEM` | Сессии веб-пользователей Django. |
| `public.file_manager_userfile` | 0 | `DORMANT` | Файлы, загруженные пользователями через модуль file manager. Модель и код есть, но данных сейчас нет. |
| `public.kladr_building` | 0 | `DORMANT` | Справочник зданий КЛАДР/адресного ядра. Для него есть модели, views и маршруты в админке, но данные не загружены. |
| `public.kladr_dataimportlog` | 0 | `DORMANT` | Журнал импортов КЛАДР. Функциональность есть, данных пока нет. |
| `public.kladr_kladraddressobject` | 0 | `DORMANT` | Адресные объекты КЛАДР. Есть модели и UI-страницы управления, но таблица пустая. |
| `public.kladr_kladrobjecttype` | 0 | `DORMANT` | Типы адресных объектов КЛАДР. Структура существует, но не заполнена. |
| `public.kladr_servicearea` | 0 | `DORMANT` | Зоны обслуживания на базе КЛАДР. Функциональность включена, данных нет. |
| `public.kladr_servicearea_buildings` | 0 | `DORMANT` | Таблица связи зон обслуживания и зданий КЛАДР. Работает как техническая связка, но пока пустая. |
| `public.llm_request_log` | 21772 | `ACTIVE` | Основной детальный лог LLM-вызовов: промпты, ответы, стоимость, связка с сессиями. Используется `ai_agent_service.py`, `trace_report_service.py`, `main_agent.py`. |
| `public.llm_response_cache` | 0 | `UNDER_REVIEW` | Пустой кэш LLM-ответов. Прямых обращений не найдено, но итоговый статус будет определен после завершения описания AI-подсистем. |
| `public.llm_tester_llmtestresult` | 457 | `ACTIVE` | Результаты тестов LLM-шаблонов и экспериментов. Используется приложением `llm_tester`. |
| `public.llm_tester_promptpreset` | 16 | `ACTIVE` | Пресеты тестовых промптов для LLM. |
| `public.llm_tester_prompttemplate` | 34 | `ACTIVE` | Шаблоны промптов для модуля тестирования LLM. |
| `public.message_handler_apierrorlog` | 7 | `ACTIVE` | Лог ошибок внешнего/API-взаимодействия в message handler. |
| `public.message_handler_communicativescript` | 1 | `ACTIVE` | Коммуникативные скрипты и шаблоны фраз бота. |
| `public.nsi_company` | 5 | `ACTIVE` | Текущий справочник компаний. Используется новым контуром ролей и заявок. |
| `public.nsi_equipmenttype` | 0 | `DORMANT` | Справочник типов оборудования. Модель есть, данных пока нет. |
| `public.portal_aiprompt` | 0 | `DORMANT` | Таблица prompt-объектов портала. Модель есть, но данных и явных живых обращений сейчас не видно. |
| `public.portal_company` | 0 | `CANDIDATE_REMOVE` | Старый дубль компаний, вытеснен `nsi_company`. Текущих обращений не найдено. |
| `public.portal_equipmenttype` | 0 | `CANDIDATE_REMOVE` | Старый дубль типов оборудования, вытеснен `nsi_equipmenttype`. |
| `public.portal_semanticpattern` | 0 | `DORMANT` | Семантические паттерны для распознавания/поиска. Модель есть, но рабочие данные отсутствуют. |
| `public.portal_userprofile` | 9 | `ACTIVE` | Профили пользователей портала: привязка к компании, подразделению и бизнес-ролям. |
| `public.prompt_template_versions` | 0 | `UNDER_REVIEW` | Старая таблица версий промптов. В текущем коде прямых ссылок нет, но окончательный статус будет определен после описания llm-tester и AI-слоя. |
| `public.prompt_templates` | 0 | `UNDER_REVIEW` | Старая таблица шаблонов промптов. Прямых живых ссылок не найдено, но решение об удалении отложено. |
| `public.ref_categories` | 11 | `ACTIVE` | Текущий справочник категорий услуг ЖКХ. Используется `services_catalog`, `message_handler`, `main_agent`. |
| `public.ref_localization` | 0 | `DORMANT` | Справочник локализаций услуг. Архитектурно нужен, но фактически сейчас пуст. Это не кандидат на удаление, а кандидат на дозаполнение. |
| `public.ref_pricing_units` | 0 | `CANDIDATE_REMOVE` | Пустой справочник единиц тарификации/ценообразования. В текущем коде не найден. |
| `public.ref_routes` | 1 | `CANDIDATE_REMOVE` | Старый справочник маршрутов в `public`. Новый контур использует `request_mgmt.route_ref`. |
| `public.ref_service_types` | 0 | `DORMANT` | Справочник типов услуги. Нужен для FK-структуры `services_catalog`, но сейчас пуст. |
| `public.ref_tags_embeddings` | 0 | `CANDIDATE_REMOVE` | Таблица embedding-тегов, которая уже помечена как удаленная в `vector_search_service.py`. |
| `public.service_objects` | 0 | `DORMANT` | Объекты обслуживания. На них ссылаются модели `portal.ServiceObject` и архитектура `work_orders`, но данных сейчас нет. |
| `public.service_tags_backup` | 416 | `ARCHIVE` | Архив/резерв старых тегов услуг. В текущем коде не используется. |
| `public.services_catalog` | 44 | `ACTIVE` | Основной текущий каталог услуг ЖКХ. Ключевая рабочая таблица для классификации и маршрутизации. |
| `public.services_catalog_backup` | 78 | `ARCHIVE` | Историческая резервная копия каталога услуг до сокращения/нормализации. |
| `public.services_catalog_before_fk_restore` | 44 | `ARCHIVE` | Снимок каталога перед восстановлением FK-структуры. |
| `public.services_catalog_old` | 78 | `ARCHIVE` | Старый вариант каталога услуг. |
| `public.tmpoldadres` | 0 | `CANDIDATE_REMOVE` | Временная/черновая таблица старых адресов. Живого кода вокруг нее нет. |
| `public.units` | 0 | `CANDIDATE_REMOVE` | Старый справочник помещений/квартир. В текущем коде используется только в SQL-фиксе и старой схеме связей. |
| `public.users` | 1 | `CANDIDATE_REMOVE` | Остаток старой пользовательской таблицы до перехода на `auth_user`. Текущий проект живет на Django users. |
| `request_mgmt.company_department` | 12 | `ACTIVE` | Подразделения компаний для маршрутизации, ролей и диспетчеризации заявок. |
| `request_mgmt.company_object_service_period` | 0 | `DORMANT` | Периоды обслуживания объектов по компании. Структура предусмотрена, но пока не заполнена. |
| `request_mgmt.company_route_mapping` | 8 | `ACTIVE` | Правила привязки компаний к маршрутам обработки заявок. |
| `request_mgmt.contractor_organization` | 3 | `ACTIVE` | Справочник подрядных организаций в новом контуре работ. |
| `request_mgmt.notification_outbox` | 0 | `DORMANT` | Исходящая очередь уведомлений по заявкам. Архитектурно предусмотрена, фактически пока не работает. |
| `request_mgmt.request_intake` | 0 | `DORMANT` | Входящий слой заявок из внешних каналов. По архитектуре это старт контура, но в реальных данных пока не используется. |
| `request_mgmt.route_ref` | 5 | `ACTIVE` | Новый рабочий справочник маршрутов в схеме `request_mgmt`. |
| `request_mgmt.sla_instance` | 0 | `DORMANT` | Экземпляры SLA по конкретным заявкам. Модель живая, но записи пока не создаются. |
| `request_mgmt.sla_policy` | 30 | `ACTIVE` | Рабочие SLA-политики по услугам, компаниям и приоритетам. |
| `request_mgmt.user_company_membership` | 11 | `ACTIVE` | Основная таблица членства пользователя в компании/подразделении/роли. Ключевая для авторизации нового контура. |
| `request_mgmt.work_order` | 23 | `ACTIVE` | Главная текущая таблица заявок. Новый контур заявок реально работает на ней. |
| `request_mgmt.work_order_attachment` | 0 | `DORMANT` | Вложения к заявкам нового контура. Таблица предусмотрена, фактических данных нет. |
| `request_mgmt.work_order_event_log` | 0 | `DORMANT` | Подробный журнал событий по заявкам нового контура. По архитектуре должен заполняться, но сейчас пуст. |
| `request_mgmt.work_order_status_history` | 36 | `ACTIVE` | История смены статусов заявок. Это реально заполняемая часть нового контура. |
| `request_mgmt.work_order_status_ref` | 8 | `ACTIVE` | Справочник статусов нового контура заявок. |
| `request_mgmt.work_order_status_transition` | 10 | `ACTIVE` | Допустимые переходы между статусами нового контура. |

## Что точно живое сейчас

### Новый рабочий контур

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

Подтверждение:
- приложение `work_orders` подключено в `komunal_dom/settings.py`
- маршруты `work_orders/` подключены в `komunal_dom/urls.py`
- `work_orders/views.py` активно работает через ORM `WorkOrder.objects...`

### Старый, но еще рабочий контур

- `public.bot_service_requests`

Подтверждение:
- `portal/urls.py` держит рабочие маршруты исполнителя `/executor/...`
- `portal/views.py` делает `SELECT/UPDATE` в `bot_service_requests`
- в таблице есть 4 записи

### Отдельный внешний контур нормативного консультанта

- UI страница: `/regulatory-chat/`
- фронтенд JS: `portal/templates/portal/normative_chat.html` + `static/js/normative-chat.js`
- backend: `nginx :8002 -> 127.0.0.1:8001`
- процесс: `python3 main_cpu.py` из `/home/olga/normativ_docs/Волков/vector-db-test/backend`

Вывод:
- это реальная отдельная подсистема;
- она не подтверждена как потребитель таблиц `ai_*` из PostgreSQL проекта;
- ее надо учитывать в новой общей архитектурной карте.

## Главные кандидаты на удаление

Статус этого раздела: **предварительный и частично замороженный**.
После замечания пользователя из списка исключены таблицы `ai_*` до завершения архитектурного описания подсистем.

Безопасные кандидаты после контрольного backup:

- `public.portal_company`
- `public.portal_equipmenttype`
- `public.ref_pricing_units`
- `public.ref_tags_embeddings`
- `public.tmpoldadres`
- `public.users`

Кандидаты на удаление, но лучше сначала подтвердить, что они не нужны для редких операций/скриптов:

- `public.debug_span_log`
- `public.debug_trace_log`
- `public.units`
- `public.ref_routes`

Таблицы, решение по которым **отложено до завершения архитектурного анализа**:

- `public.ai_cost_tracking`
- `public.ai_model_pricing`
- `public.ai_models`
- `public.ai_providers`
- `public.ai_request_history`
- `public.ai_type_of_service`
- `public.prompt_template_versions`
- `public.prompt_templates`
- `public.llm_response_cache`

Архивы, которые можно либо вынести в dump, либо удалить после утверждения:

- `public.bot_service_requests_backup`
- `public.service_tags_backup`
- `public.services_catalog_backup`
- `public.services_catalog_before_fk_restore`
- `public.services_catalog_old`

## Риски и аномалии

1. `bot_service_requests` еще жив.
Старую форму заявок нельзя удалять, пока не переведены маршруты `portal.executor_*` на `work_order`.

2. Новый контур не полностью дозаполнен.
`request_intake`, `sla_instance`, `work_order_event_log`, `work_order_attachment` пустые, хотя архитектурно предусмотрены.

3. Справочники для FK-структуры частично пусты.
`ref_service_types`, `ref_localization`, `service_objects` пустые, хотя новый каталог услуг уже используется.

4. В БД есть явный слой архивных таблиц.
Особенно это заметно по `services_catalog_*`, `service_tags_backup`, `bot_service_requests_backup`.

## Практический вывод

Если задача сейчас именно почистить БД без риска:

1. Не трогать `request_mgmt.*`, `services_catalog`, `dialog_logs`, `llm_request_log`, `auth_*`, `portal_userprofile`, `nsi_company`, `ref_categories`, `llm_tester_*`.
2. Не удалять `bot_service_requests`, пока старые `portal/executor/*` маршруты не переведены на `work_order`.
3. Сначала вынести в отдельный SQL dump архивные и legacy-таблицы.
4. Потом удалять явные рудименты из списка `CANDIDATE_REMOVE`.
