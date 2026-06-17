# Индекс подсистем и терминов

Дата актуализации: 2026-04-29

## Рабочие подсистемы

1. `message_handler` — чатовый intake
2. `work_orders` — жизненный цикл заявок АДС
3. `portal` — кабинеты и административный UI
4. `llm_tester` — тестирование production-промптов по slug
5. `address` — целевая плоская адресная схема

## Ключевые термины

### Новый контур заявок

Рабочая заявка живет в `request_mgmt.work_order`.

### Chat intake

`/chat/` и связанные API:

- создают `work_order` напрямую после подтверждения;
- не создают `request_intake`;
- пишут intake-payload в `work_order_event_log`.

### Address v2

Новая адресная модель:

- `address.building`
- `address.unit`

Старый `kladr` — это legacy-слой и источник миграции, а не целевая модель.

### Объект обслуживания

- дом: `service_object.unit_id is null`
- квартира/помещение: `service_object.unit_id is not null`

## Что считать устаревшим

- `request_intake` как обязательный runtime-слой;
- `work_order_status_transition` как рабочий справочник переходов;
- `notification_outbox` как рабочую очередь;
- хранение домового FIAS-ID в `service_object`.
