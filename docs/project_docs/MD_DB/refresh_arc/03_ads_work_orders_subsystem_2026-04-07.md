# АДС / Work Orders

Дата актуализации: 2026-04-29

## Текущее состояние

- Центральная сущность: `request_mgmt.work_order`.
- `request_intake` удален из runtime.
- `work_order_status_transition` удален из runtime-модели и не должен использоваться как источник правил.
- `notification_outbox` удален из runtime-модели.
- Движение по статусам управляется кодом workflow и UI-кнопками жизненного цикла.

## Основные таблицы

### Рабочие

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

### Удалены из runtime

- `request_mgmt.request_intake`
- `request_mgmt.work_order_status_transition`
- `request_mgmt.notification_outbox`

## Адресная модель АДС

АДС больше не должен считать адрес свойством `service_object`.

### Источник истины по дому

`address.building`:

- `id`
- `fias_guid`
- `street_fias_guid`
- `house_number`
- `full_address`
- `geo_lat`
- `geo_lon`
- `timezone`

### Источник истины по квартире/помещению

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
- `is_active`

Правило:

- `unit_id is null` — объект обслуживания уровня дома
- `unit_id is not null` — объект обслуживания уровня квартиры/помещения

Поле `fias_house_object_id` считается ошибочной денормализацией и удаляется.

## Привязка к компании

Источник истины: `request_mgmt.company_object_service_period`.

Проверка конфликта:

- объект нельзя привязать к другой компании, если есть пересекающийся активный период;
- повторная привязка к той же компании должна быть идемпотентной.

## Ручной ввод и импорт объектов

При ручном вводе или импорте:

1. подтверждается дом через FIAS;
2. если нет `street_fias_guid`, дом не сохраняется;
3. если найден дом, создается или используется `address.building`;
4. всегда создается или используется домовой `service_object`;
5. если переданы квартиры/помещения, создаются или используются `address.unit`;
6. для квартир создаются отдельные `service_object`;
7. привязки к компании создаются и для дома, и для квартир.

## SLA

В runtime используются три линии SLA:

- реакция
- локализация
- выполнение

Источник норматива: `request_mgmt.sla_policy`.
Источник факта по заявке: `request_mgmt.sla_instance`.

`priority_code` больше не должен быть обязательной осью SLA-архитектуры.

## Фото по заявке

Фото результата заявки хранятся в `request_mgmt.work_order_attachment`.

Переходы:

- `in_progress -> localized`
- `localized -> completed`

требуют проверок по `resolution_text`, а при отсутствии фото должны показывать отдельное подтверждение пользователю.

## Интеграция с чатовым intake

- чатовый intake создает `work_order` напрямую;
- диагностический intake payload хранится в `work_order_event_log.event_payload_json`;
- адрес в payload должен ссылаться на `building_id`, `unit_id`, `service_object_id`, `fias_guid`, `street_fias_guid`, `house_number`.
