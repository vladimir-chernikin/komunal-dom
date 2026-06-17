# NSI / Identity / Address catalog

Дата актуализации: 2026-04-29

## Что считать рабочим контуром

### Пользователи и роли

- `auth_user`
- `portal_userprofile`
- `request_mgmt.user_company_membership`
- `request_mgmt.company_department`

Бизнес-роль пользователя должна браться из `user_company_membership`, а не из старых полей профиля.

### Каталоги услуг

- `services_catalog`
- `ref_categories`
- `ref_service_types`
- `ref_localization`
- `nsi_company`

### Адресный контур

Целевая адресная схема:

- `address.building`
- `address.unit`

Старый `kladr` больше не должен описываться как целевая модель. Его роль:

- legacy-слой;
- источник миграции;
- временная опора для перехода.

## Что хранится в адресе

### Дом

`address.building`:

- `fias_guid`
- `street_fias_guid`
- `house_number`
- `full_address`
- `geo_lat`
- `geo_lon`
- `timezone`

### Помещение

`address.unit`:

- `building_id`
- `unit_number`
- `fias_guid`

## Важное правило идентичности

FIAS-идентификаторы дома должны храниться только в адресных таблицах.

Нельзя считать нормальной архитектурой:

- хранение house FIAS ID внутри `service_object`;
- дублирование домового FIAS-ID в нескольких слоях.

## Объекты обслуживания

`portal.service_object` хранит только ссылку на адрес:

- `building_id`
- `unit_id`

Правило:

- домовой объект обслуживания: `unit_id is null`
- квартирный объект обслуживания: `unit_id is not null`

## Что считать устаревшим

- любые описания, где `building-level` адрес объявлен достаточным без поддержки квартирных объектов;
- любые схемы, где квартира “отложена на потом” как несущественная;
- любые описания, где `kladr.Building` считается целевой адресной сущностью.
