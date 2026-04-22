# Черновик разнесения таблиц по схемам БД

Дата: 2026-04-07
Статус: draft / без физического удаления таблиц

Цель документа: заранее разложить оставшиеся таблицы по будущим схемам, чтобы на следующем этапе можно было сделать миграцию по схемам без повторного архитектурного анализа.

## 1. Принцип разбиения

Разделяем не по текущему историческому происхождению таблиц, а по подсистеме-владельцу данных.

Правило:

- одна таблица должна иметь одного главного владельца;
- кросс-подсистемные ссылки допустимы, но сами данные не должны "болтаться" между схемами;
- общие справочники и идентификация выносятся отдельно от процессных таблиц.

## 2. Предлагаемые схемы

### `identity`

Назначение:

- пользователи;
- роли и права;
- профили;
- memberships.

Таблицы-кандидаты:

- `public.auth_user`
- `public.auth_group`
- `public.auth_group_permissions`
- `public.auth_permission`
- `public.auth_user_groups`
- `public.auth_user_user_permissions`
- `public.django_admin_log`
- `public.django_content_type`
- `public.django_session`
- `public.portal_userprofile`
- `request_mgmt.user_company_membership`

Комментарий:

- `auth_*` можно оставить в `public` как системное ядро Django, но концептуально это схема `identity`.

### `nsi`

Назначение:

- компании;
- оргструктура;
- общие классификаторы;
- объекты обслуживания.

Таблицы-кандидаты:

- `public.nsi_company`
- `request_mgmt.company_department`
- `request_mgmt.contractor_organization`
- `request_mgmt.route_ref`
- `request_mgmt.company_route_mapping`
- `public.ref_categories`
- `public.ref_service_types`
- `public.ref_localization`
- `public.kladr_*`
- `public.portal_serviceobject`

Комментарий:

- это слой нормативно-справочной информации, а не процессные данные.

### `service_catalog`

Назначение:

- единый каталог услуг и его техслужебные расширения.

Таблицы-кандидаты:

- `public.services_catalog`
- `public.service_tags`
- `public.service_tags_backup`
- `public.services_catalog_backup`
- `public.services_catalog_before_fk_restore`
- `public.services_catalog_old`

Комментарий:

- боевая таблица одна: `services_catalog`;
- backup/old-таблицы должны быть позже вынесены в архивную схему или удалены после сверки.

### `chatbot`

Назначение:

- ИИ-чат приема обращений;
- логика LLM;
- диалоги;
- отладка и трассировка.

Таблицы-кандидаты:

- `public.dialog_logs`
- `public.llm_request_log`
- `public.message_handler_communicativescript`
- `public.message_handler_apierrorlog`
- `public.llm_tester_testcase`
- `public.llm_tester_testresult`
- `public.llm_tester_promptsnapshot`
- `public.llm_tester_testsuite`
- `public.llm_response_cache`

Комментарий:

- `request_intake` логически тоже примыкает к приему обращений, но если он становится входом в АДС-пайплайн, его лучше держать рядом с `work_order`.

### `regulatory_ai`

Назначение:

- консультант по законодательству;
- модели/провайдеры/тарификация ИИ, если они реально принадлежат именно этому контуру.

Таблицы-кандидаты:

- `public.ai_cost_tracking`
- `public.ai_model_pricing`
- `public.ai_models`
- `public.ai_providers`
- `public.ai_request_history`
- `public.ai_type_of_service`

Комментарий:

- эти таблицы не надо удалять "по инерции";
- их надо окончательно закрепить за консультантом или общим AI-инфраструктурным слоем после второго прохода по коду.

### `ads`

Назначение:

- жизненный цикл заявки;
- маршрутизация исполнения;
- SLA;
- фото результата;
- журнал событий.

Таблицы-кандидаты:

- `request_mgmt.work_order`
- `request_mgmt.work_order_status_ref`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.work_order_status_history`
- `request_mgmt.work_order_event_log`
- `request_mgmt.work_order_attachment`
- `request_mgmt.sla_policy`
- `request_mgmt.sla_instance`
- `request_mgmt.notification_outbox`
- `request_mgmt.request_intake`

Комментарий:

- это основной процессный контур АДС;
- `request_intake` можно оставить здесь, если он считается официальным входным конвейером заявки.

### `operations_archive`

Назначение:

- резервные, legacy и transitional таблицы, которые не участвуют в живом коде, но пока нужны как архив.

Таблицы-кандидаты:

- `public.bot_service_requests_backup`
- `public.prompt_templates`
- `public.prompt_template_versions`
- `public.tmpoldadres`
- `public.users`
- backup/old таблицы каталога услуг

Комментарий:

- `public.bot_service_requests` и `public.bot_service_requests_backup` на текущем шаге уже выведены из runtime и подлежат удалению/удалены миграцией legacy executor cleanup.

## 3. Куда НЕ надо спешить переносить

Под вопросом до второго круга анализа:

- `public.ai_*`
- `public.prompt_templates*`
- `public.llm_response_cache`

Причина:

- по названиям они выглядят как кандидаты в мусор;
- но фактически могут обслуживать сразу несколько AI-подсистем.

## 4. Предлагаемая очередность рефакторинга по схемам

1. Зафиксировать owner для каждой таблицы.
2. Вычистить legacy runtime и backup-рудименты.
3. Разделить `identity` и `nsi`.
4. Отделить `service_catalog`.
5. Отделить `chatbot` от `ads`.
6. Отдельно решить судьбу `regulatory_ai`.
7. После этого физически переносить таблицы по схемам и обновлять ORM/meta/db_table.

## 5. Что важно перед реальным переносом

- проверить raw SQL по всему проекту;
- проверить все unmanaged-модели;
- проверить `search_path` PostgreSQL;
- проверить внешние сервисы, которые ходят в БД напрямую;
- отдельно подготовить plan по обновлению `db_table`, SQL comments и `/db-sql/`.

## 6. Вывод

Будущее разнесение БД логично строить вокруг 6 владельцев:

- `identity`
- `nsi`
- `service_catalog`
- `chatbot`
- `regulatory_ai`
- `ads`

Все архивы и transitional-слой должны либо уйти в `operations_archive`, либо быть удалены после верификации.

## 7. Обновление 2026-04-09

### ADS как владелец нумератора

Для будущего разнесения по схемам важно зафиксировать: нумератор заявок — это часть процессного контура `ads`, а не `identity` и не `nsi`.

Причина:

- номер заявки формируется в `request_mgmt.work_order`;
- номер зависит от компании, но сам счетчик живет внутри жизненного цикла заявок;
- поле `company_sequence_no` должно оставаться в схеме `ads` рядом с `work_order`.

Текущий стандарт номера:

- `{company_id}-{company_sequence_no}`;
- пример: `3-7`, `4-2`.

### ADS как владелец SLA

После упрощения модели SLA подсистема `ads` окончательно владеет такими сущностями:

- `request_mgmt.sla_policy`;
- `request_mgmt.sla_instance`.

При этом внутри `ads` нужно считать канонической только трехлинейную модель:

- `SLA реакции`;
- `SLA локализации`;
- `SLA выполнения`.

Из будущей схемы `ads` уже исключены как рабочие сущности:

- аварийный разрез SLA на уровне `sla_policy`;
- контакт с заявителем как отдельный SLA-таймер;
- автозакрытие как отдельный SLA-таймер;
- старое имя `work_start_*` как самостоятельный архитектурный термин.

### Важное следствие для будущего schema split

При переносе таблиц по схемам нельзя снова смешивать:

- код компании и справочник компаний (`nsi`) — остаются внешней ссылкой;
- номер заявки и SLA-нормативы (`ads`) — остаются внутри процессной схемы заявок.

Иначе при следующем рефакторинге снова появится путаница между общими справочниками и процессной логикой АДС.
