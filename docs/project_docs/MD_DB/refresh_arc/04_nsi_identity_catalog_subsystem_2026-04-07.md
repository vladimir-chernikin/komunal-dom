# Подсистема: НСИ / идентификация / каталог услуг

Дата: 2026-04-07

## Обновление 2026-04-13

- В `kladr` добавлены FIAS-реквизиты для улиц и зданий: `fias_object_id`, `fias_object_guid`, `fias_level_id`, `fias_address_type`, а для зданий еще и `fias_full_name`.
- Building-level FIAS mapping стал частью рабочего контура: по FIAS ID/GUID можно получить внутренние `building_id` и `service_object_id`.
- `service_objects` нельзя считать пустым целевым слоем: таблица живая и используется новым chat-intake.
- Привязка квартир к ФИАС пока не реализована. На текущем этапе canonical object identity для intake строится на уровне здания.
- Прямая матрица `service_object -> company` в данных все еще не стабилизирована, поэтому выбор компании для чатовых заявок пока остается временной эвристикой.

## Назначение

Это сквозной доменный слой, который обеспечивает:
- компании;
- пользователей и роли;
- привязку пользователя к компании и подразделению;
- каталог услуг;
- базовые справочники для AI и АДС.

Это не один Django app, а несколько связанных слоев:
- `auth`
- `portal`
- `nsi`
- `work_orders` membership-слой

## Основные сущности

### Пользовательская идентификация

- `auth_user`
- `portal_userprofile`
- `request_mgmt.user_company_membership`

### Организационная структура

- `nsi_company`
- `request_mgmt.company_department`

### Каталог услуг и классификация

- `services_catalog`
- `ref_categories`
- `ref_service_types`
- `ref_localization`
- `service_objects`

## 1. Пользователи и роли

### Django user

Факт:
- основная таблица пользователя: `auth_user`

Пруф:
- встроенный Django auth;
- живое использование по всему проекту.

### Профиль портала

Файл:
- [portal/models.py](/var/www/komunal-dom_ru/portal/models.py)

Таблица:
- `portal_userprofile`

Что хранит:
- роль старого/переходного уровня;
- часовой пояс;
- телефон, адрес;
- primary company / primary department;
- специализацию и должность.

### Membership нового контура

Файл:
- [work_orders/models.py](/var/www/komunal-dom_ru/work_orders/models.py)

Таблица:
- `request_mgmt.user_company_membership`

Что хранит:
- связь user <-> company <-> department <-> role;
- именно этот слой сейчас критичен для нового role-based поведения.

## 2. Компании и подразделения

### Компании

Файл:
- [nsi/models.py](/var/www/komunal-dom_ru/nsi/models.py)

Таблица:
- `nsi_company`

Факт:
- это текущий рабочий справочник компаний;
- `portal_company` выглядит как старый дубль и не подтвержден как рабочий.

### Подразделения

Файл:
- [work_orders/models.py](/var/www/komunal-dom_ru/work_orders/models.py)

Таблица:
- `request_mgmt.company_department`

Факт:
- подразделения уже относятся к новому контуру и нужны не только АДС, но и общему role/access слою.

## 3. Каталог услуг

Файл:
- [portal/models.py](/var/www/komunal-dom_ru/portal/models.py)

Таблица:
- `services_catalog`

Факты:
- это unmanaged-модель;
- каталог услуг реально используется AI-слоем;
- модель содержит как FK-поля, так и временно сохраненные текстовые поля обратной совместимости.

Это очень важный момент:
- `services_catalog` уже является общим сквозным доменным справочником;
- он нужен и AI-чатботу, и будущей АДС-маршрутизации.

## 4. Справочники классификации

Файл:
- [nsi/models.py](/var/www/komunal-dom_ru/nsi/models.py)

Таблицы:
- `ref_categories`
- `ref_service_types`
- `ref_localization`

Факты:
- код AI-слоя реально читает эти таблицы;
- `ref_categories` уже заполнен;
- `ref_service_types` и `ref_localization` архитектурно живые, но сейчас пусты в данных.

Следствие:
- это не кандидаты на удаление;
- это сквозной доменный слой, который надо привести в консистентное состояние.

## 5. Объекты обслуживания

Файл:
- [portal/models.py](/var/www/komunal-dom_ru/portal/models.py)
- [kladr/fias_service.py](/var/www/komunal-dom_ru/kladr/fias_service.py)

Таблица:
- `service_objects`

Факт:
- модель живая;
- таблица не пустая и уже участвует в рабочем intake-контуре;
- building-level объекты уже используются как минимальная единица адресной идентификации;
- АДС-архитектура уже ссылается на нее.

Это означает:
- `service_objects` — часть целевой доменной модели, а не просто архив.

## 5.1. FIAS Identity Layer

Новый смысловой слой:
- `kladr_kladraddressobject` и `kladr_building` теперь хранят внешнюю идентичность ФИАС;
- `kladr.fias_service.FiasAddressService` выполняет поиск здания по ФИАС, привязку локального здания к house-level объекту ФИАС и обратное разрешение `FIAS -> internal IDs`.

Практический эффект:
- поиск обслуживаемого адреса теперь можно строить по устойчивому внешнему идентификатору;
- последующая привязка квартир может быть добавлена без смены building-level схемы.

## 6. Где это реально используется

### В AI чатботе

Пруфы:
- [main_agent.py](/var/www/komunal-dom_ru/main_agent.py)
- [filter_detection_service.py](/var/www/komunal-dom_ru/filter_detection_service.py)
- [semantic_search_service.py](/var/www/komunal-dom_ru/semantic_search_service.py)

Факты:
- чат-бот реально использует `services_catalog` и `ref_*`.

### В АДС

Пруфы:
- [work_orders/models.py](/var/www/komunal-dom_ru/work_orders/models.py)
- [work_orders/views.py](/var/www/komunal-dom_ru/work_orders/views.py)

Факты:
- `WorkOrder` завязан на компанию, подразделение, услугу, объект, пользователя и membership.

### В portal / кабинетах

Пруфы:
- [portal/models.py](/var/www/komunal-dom_ru/portal/models.py)
- [portal/views.py](/var/www/komunal-dom_ru/portal/views.py)
- [portal/admin_views.py](/var/www/komunal-dom_ru/portal/admin_views.py)

Факты:
- portal использует `UserProfile`, `Company`, `WorkOrder`, membership и статистику по ролям.

## Основные проблемные зоны

1. Два слоя ролей живут одновременно:
- `portal_userprofile.role`
- `request_mgmt.user_company_membership.role_code`

2. Каталог услуг уже общий, но еще несет transitional поля.

3. Есть старые дубли:
- `portal_company`
- `portal_equipmenttype`

4. Есть целевые, но пока не до конца заполненные доменные сущности:
- `ref_service_types`
- `ref_localization`

## Предварительная целевая ответственность подсистемы

Эта подсистема должна стать единым слоем:
- identity;
- role model;
- company / department structure;
- service catalog;
- service taxonomy;
- service objects.

Именно ее потом логично стабилизировать раньше, чем глубоко чистить AI или АДС.
