# Claude Subsystems Fact Map

Дата актуализации: 2026-04-29

## Подтвержденные факты

- Новый контур заявок живет в `request_mgmt.work_order`.
- Чатовый intake не создает `request_intake`.
- История статусов хранится в `request_mgmt.work_order_status_history`.
- SLA работает через `request_mgmt.sla_policy` и `request_mgmt.sla_instance`.
- Адресный target-контур: `address.building` и `address.unit`.
- `service_object` хранит только `building_id` и `unit_id`.
- Квартира является полноценным объектом обслуживания, если `unit_id` заполнен.
- `llm_request_log` использует `caller_service`, `prompt_slug`, `prompt_source`.

## Удалено из runtime

- `request_mgmt.request_intake`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.notification_outbox`
- `portal_aiprompt`
- `message_handler_communicativescript`

## Что считать legacy

- `kladr` как целевую адресную модель;
- хранение FIAS house id в `service_object`;
- сценарные фразы и промпты в старых справочниках вместо `llm_tester` и кодового orchestrator-flow.
