# Архитектура управления заявками

Дата актуализации: 2026-04-29

## Коротко

Текущий рабочий контур заявок живет в `request_mgmt.work_order`.

Промежуточный документ `request_intake` больше не является runtime-сущностью.  
Чатовый intake создает `work_order` напрямую, а диагностический payload пишет в `request_mgmt.work_order_event_log`.

## Рабочие таблицы

- `request_mgmt.work_order`
- `request_mgmt.work_order_status_ref`
- `request_mgmt.work_order_status_history`
- `request_mgmt.work_order_event_log`
- `request_mgmt.work_order_attachment`
- `request_mgmt.sla_policy`
- `request_mgmt.sla_instance`
- `request_mgmt.route_ref`
- `request_mgmt.company_route_mapping`
- `request_mgmt.company_department`
- `request_mgmt.user_company_membership`
- `request_mgmt.company_object_service_period`
- `request_mgmt.contractor_organization`

## Удаленные из runtime сущности

- `request_mgmt.request_intake`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.notification_outbox`

Они могут еще встречаться в старых миграциях, архивных файлах и `.bak`, но не должны использоваться в рабочем коде.

## Жизненный цикл заявки

Основная последовательность:

1. `new_registered`
2. `accepted_by_executor`
3. `in_progress`
4. `localized`
5. `completed`
6. `closed`

Ручной выбор статуса допустим только в админке для superuser.  
Рабочий UI должен двигать заявку только стандартными lifecycle-кнопками.

## SLA

SLA опирается на:

- норматив: `request_mgmt.sla_policy`
- факт: `request_mgmt.sla_instance`

Используются три линии:

- SLA реакции
- SLA локализации
- SLA выполнения

## Адрес и объект обслуживания

### Дом

`address.building`:

- `id`
- `fias_guid`
- `street_fias_guid`
- `house_number`
- `full_address`

### Помещение

`address.unit`:

- `id`
- `building_id`
- `unit_number`
- `fias_guid`

### Объект обслуживания

`portal.service_object`:

- `service_object_id`
- `building_id`
- `unit_id`

Правило:

- `unit_id is null` — дом
- `unit_id is not null` — квартира/помещение

Поле `fias_house_object_id` должно быть удалено как дубль адресной идентичности.

## Привязка к компании

Источник истины: `request_mgmt.company_object_service_period`.

Компания для intake определяется только через:

`service_object + дата -> company_object_service_period -> company`

Эвристический выбор компании считать ошибкой.

## Интеграция с ботом

Бот:

- ищет дом по FIAS;
- использует fallback `street_fias_guid + house_number`;
- квартиру ищет только в локальных объектах после определения дома;
- не блокирует создание заявки, если квартира не найдена, но дом обслуживается.
