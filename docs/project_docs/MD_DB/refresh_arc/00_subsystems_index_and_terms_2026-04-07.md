# Подсистемы и термины проекта komunal-dom.ru

Дата: 2026-04-07

Документ-роутер:
- объясняет рабочие термины;
- показывает разрез проекта по подсистемам;
- ссылается на отдельные fact-based документы.

## Что значит `legacy`

`Legacy` в этом проекте не означает "мусор" или "можно удалить".

Здесь это значит:
- старый контур или старый способ работы;
- он уже не является целевой архитектурой;
- но он все еще может обслуживать живой маршрут, живой экран или рабочую таблицу;
- удалять его без переноса поведения нельзя.

Пример:
- новый целевой контур заявок: `request_mgmt.work_order`
- legacy-контур исполнителя: `/executor/...` через `public.bot_service_requests`

## Что значит "новый контур заявок живет в `request_mgmt.work_order`, а legacy `/executor/...` все еще работает через `bot_service_requests`"

Это означает следующее:

1. В проекте уже создана новая предметная модель заявок.
Она реализована в Django app `work_orders` и хранит заявки в таблице `request_mgmt.work_order`.

2. Для нее есть отдельные экраны и логика.
Например:
- `/work_orders/...`
- ORM-модели `WorkOrder`, `WorkOrderStatusRef`, `UserCompanyMembership` и др.

3. Но часть старых маршрутов исполнителя еще не переведена на эту модель.
Маршруты:
- `/executor/take/<id>/`
- `/executor/arrived/<id>/`
- `/executor/complete/<id>/`
- `/executor/upload-photo/<id>/`
- `/executor/report/<id>/`

4. Эти старые маршруты до сих пор читают и обновляют таблицу `public.bot_service_requests`.
То есть в системе одновременно существуют:
- новый контур заявок;
- старый, но еще работающий контур исполнителя.

Практический смысл:
- `bot_service_requests` пока нельзя считать "мертвым";
- сначала надо переподключить `/executor/...` к `work_order`, и только потом обсуждать зачистку legacy-слоя.

## Что уже подтверждено

- `/chat/` сейчас не создает `request_intake` и не пишет в `work_order`
- `/regulatory-chat/` это UI внутри Django, но backend у него внешний
- `/db-sql/` читает описания таблиц из PostgreSQL comments
- `llm_request_log` реально живой
- `services_catalog` и `ref_*` реально живые
- `ai_*` таблицы пока переведены в `UNDER_REVIEW`, а не в "удалять"

## Пакет документов по подсистемам

1. [01_chatbot_intake_subsystem_2026-04-07.md](C:\codex\AdminSSH\01_chatbot_intake_subsystem_2026-04-07.md)
2. [02_regulatory_consultant_subsystem_2026-04-07.md](C:\codex\AdminSSH\02_regulatory_consultant_subsystem_2026-04-07.md)
3. [03_ads_work_orders_subsystem_2026-04-07.md](C:\codex\AdminSSH\03_ads_work_orders_subsystem_2026-04-07.md)
4. [04_nsi_identity_catalog_subsystem_2026-04-07.md](C:\codex\AdminSSH\04_nsi_identity_catalog_subsystem_2026-04-07.md)
5. [05_portal_admin_support_subsystem_2026-04-07.md](C:\codex\AdminSSH\05_portal_admin_support_subsystem_2026-04-07.md)
6. [06_diagnostics_sql_observability_subsystem_2026-04-07.md](C:\codex\AdminSSH\06_diagnostics_sql_observability_subsystem_2026-04-07.md)

## Предварительный разрез проекта по подсистемам

### Бизнес-подсистемы

- Чат-бот приема заявок
- Нормативный консультант
- АДС / новый контур управления заявками

### Сквозные доменные слои

- НСИ: компании, справочники услуг, локализации, типы услуг, роли, membership
- Идентификация и профили: `auth_user`, `portal_userprofile`, `user_company_membership`

### Служебные и инженерные подсистемы

- Portal shell / кабинеты / роль-зависимая навигация
- LLM Tester
- Диалоговая трассировка
- SQL interface `/db-sql/`
- File manager
- КЛАДР-инструменты

## Где лежат серверные рабочие копии

Все актуальные артефакты по этой задаче складываются в:
- `/var/www/komunal-dom_ru/MD_DB/refresh_arc/`

