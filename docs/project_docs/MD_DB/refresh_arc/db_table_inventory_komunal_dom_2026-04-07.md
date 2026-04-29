# Инвентаризация ключевых таблиц

Дата актуализации: 2026-04-29

## Рабочий контур заявок

### ACTIVE

- `request_mgmt.work_order`
- `request_mgmt.work_order_status_ref`
- `request_mgmt.work_order_status_history`
- `request_mgmt.work_order_event_log`
- `request_mgmt.work_order_attachment`
- `request_mgmt.sla_policy`
- `request_mgmt.sla_instance`
- `request_mgmt.company_route_mapping`
- `request_mgmt.company_department`
- `request_mgmt.user_company_membership`
- `request_mgmt.company_object_service_period`
- `request_mgmt.contractor_organization`

### REMOVED_FROM_RUNTIME

- `request_mgmt.request_intake`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.notification_outbox`

## Адресный контур

### TARGET_ACTIVE

- `address.building`
- `address.unit`
- `address.import_batch`
- `address.import_row`

### LEGACY_MIGRATION_SOURCE

- `kladr_building`
- `kladr_kladraddressobject`
- `kladr_kladrobjecttype`
- `kladr_servicearea`
- `kladr_dataimportlog`
- `units`

Комментарий:

- `kladr` больше не должен считаться целевой адресной моделью;
- он используется как источник переноса данных в `address.*`.

## Чат и AI

### ACTIVE

- `dialog_logs`
- `llm_request_log`
- `message_handler_apierrorlog`
- `llm_tester_prompttemplate`
- `llm_tester_promptpreset`
- `llm_tester_llmtestresult`

### REMOVED_FROM_RUNTIME

- `portal_aiprompt`
- `message_handler_communicativescript`

## Примечания

- `work_order_event_log` — живая таблица аудита и intake-payload.
- `request_intake` не использовать как описание текущего runtime-пайплайна.
- `service_object` должен ссылаться на `address.building` и `address.unit`, а не хранить дубли адресных FIAS-полей.
