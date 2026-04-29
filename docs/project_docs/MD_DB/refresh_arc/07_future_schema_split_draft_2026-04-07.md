# Draft: схема разделения по bounded context

Дата актуализации: 2026-04-29

## Текущая опора

Если делать дальнейшее разделение схем, зафиксировать надо уже обновленное состояние, а не старый transitional слой.

## Контур заявок

Оставить в `request_mgmt`:

- `work_order`
- `work_order_status_ref`
- `work_order_status_history`
- `work_order_event_log`
- `work_order_attachment`
- `sla_policy`
- `sla_instance`
- `company_object_service_period`
- `company_route_mapping`
- `company_department`
- `user_company_membership`
- `contractor_organization`

Не возвращать в draft как живые сущности:

- `request_intake`
- `work_order_status_transition`
- `notification_outbox`

## Адресный контур

Выносить отдельно в `address`:

- `building`
- `unit`
- `import_batch`
- `import_row`

Старый `kladr` считать только migration-source.

## Контур чата

Chat intake должен оставаться отдельным runtime-контуром, но не со своей таблицей заявки.  
Результат его работы — создание записи в `request_mgmt.work_order`.

## Контур промптов

Рабочие промпты должны жить в `llm_tester` и вызываться по `slug`.  
Возврат к `AIPrompt` и `CommunicativeScript` не допускается.
