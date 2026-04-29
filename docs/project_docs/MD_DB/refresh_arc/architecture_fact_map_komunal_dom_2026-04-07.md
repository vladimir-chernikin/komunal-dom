# Architecture Fact Map

Дата актуализации: 2026-04-29

## Подтверждено кодом

### Чат

- `message_handler_service.py` принимает сообщение и ведет диалог.
- `work_orders/intake_service.py` создает `work_order` напрямую.
- `request_intake` в рабочем pipeline не участвует.

### LLM

- `llm_request_log` — живая таблица.
- лог хранит `caller_service`, `prompt_slug`, `prompt_source`.
- production-промпты должны ссылаться на `llm_tester.PromptTemplate.slug`.

### Заявки

- рабочая заявка живет в `request_mgmt.work_order`;
- история статусов — `request_mgmt.work_order_status_history`;
- аудит/diagnostic payload — `request_mgmt.work_order_event_log`;
- SLA — `request_mgmt.sla_policy` и `request_mgmt.sla_instance`.

### Адрес

- целевая схема: `address.building`, `address.unit`;
- `kladr` остается только migration-source;
- `service_object` не должен хранить домовой FIAS-ID;
- квартира ищется локально после определения дома.

## Подтверждено структурой БД

### Active

- `request_mgmt.work_order`
- `request_mgmt.work_order_status_ref`
- `request_mgmt.work_order_status_history`
- `request_mgmt.work_order_event_log`
- `request_mgmt.work_order_attachment`
- `request_mgmt.sla_policy`
- `request_mgmt.sla_instance`
- `request_mgmt.company_object_service_period`
- `request_mgmt.user_company_membership`
- `dialog_logs`
- `llm_request_log`
- `address.building`
- `address.unit`

### Removed from runtime

- `request_mgmt.request_intake`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.notification_outbox`
- `portal_aiprompt`
- `message_handler_communicativescript`

## Нормативные выводы

- компания должна определяться только через `service_object -> company_object_service_period`;
- если квартира не найдена, но дом обслуживается, заявка все равно может быть создана на домовой объект;
- `street_fias_guid + house_number` — обязательный fallback адресного поиска;
- если `street_fias_guid` не найден, дом не должен сохраняться как подтвержденный адрес.
