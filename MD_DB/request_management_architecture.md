# Архитектура подсистемы управления заявками ЖКХ

**Дата создания:** 2026-03-27
**Версия:** 1.0
**Статус:** Целевая архитектура

---

## 1. ОБЗОР

Подсистема управления заявками ЖКХ предназначена для полноценного жизненного цикла обработки обращений жителей: от приема заявки из внешних каналов до выполнения, закрытия и аналитики.

### 1.1. Основные цели

- Единая централизованная система управления заявками для нескольких компаний-заказчиков
- Полный жизненный цикл заявки: прием → маршрутизация → исполнение → контроль → закрытие
- Разделение данных по компаниям с гибкими настройками маршрутов и SLA
- Поддержка внешних подрядчиков и смешанных оргструктур
- История изменений, вложения и уведомления

### 1.2. Базовая доменная ось

```
request_intake → work_order → исполнение → закрытие
```

- **request_intake**: входящий JSON/событие из внешних каналов
- **work_order**: главная сущность заявки
- Исполнение: назначение исполнителя, статусы, SLA, события
- Закрытие: выполнение, автозакрытие, переоткрытие

### 1.3. Организация данных в БД

Все таблицы подсистемы находятся в отдельной PostgreSQL schema:
- **Schema:** `request_mgmt`
- **PK тип:** `bigint` с `identity/auto increment`
- **Обязательное поле:** `is_test boolean NOT NULL DEFAULT false`

---

## 2. СУЩНОСТИ ПОДСИСТЕМЫ

### 2.1. Документы (основные сущности)

#### 2.1.1. request_intake

**Назначение:** Регистрация входящего JSON из внешних каналов

**Ключевые поля:**
- `request_intake_id bigint PK`
- `company_id bigint NOT NULL` → `nsi_company`
- `channel_code varchar(30) NOT NULL` — канал: telegram, max, site_chat, phone, manual
- `source_payload_json jsonb NOT NULL` — сырой JSON
- `normalized_payload_json jsonb NULL` — нормализованный JSON
- `external_message_id varchar(255) NULL` — ID во внешней системе
- `message_log_ref varchar(255) NULL` — ссылка на MessageLog
- `received_at timestamptz NOT NULL` — момент получения
- `is_test boolean NOT NULL DEFAULT false`

**Индексы:**
- `company_id, received_at desc`
- `channel_code, received_at desc`
- `external_message_id`

---

#### 2.1.2. work_order

**Назначение:** Главная сущность заявки

**Ключевые поля:**
- `work_order_id bigint PK`
- `work_order_no varchar(30) NOT NULL UNIQUE` — человекочитаемый номер
- `company_id bigint NOT NULL` → `nsi_company`
- `object_id bigint NOT NULL` → `service_objects`
- `service_id bigint NOT NULL` → `services_catalog`
- `route_id bigint NOT NULL` → `request_mgmt.route_ref`
- `department_id bigint NOT NULL` → `request_mgmt.company_department`
- `responsible_user_id bigint NULL` → `auth_user`
- `request_intake_id bigint NULL UNIQUE` → `request_mgmt.request_intake`
- `creation_source varchar(30) NOT NULL` — bot_json, manual_*
- `original_request_text text NOT NULL` — текст обращения
- `additional_info_text text NULL` — доп. сведения
- `resolution_text text NULL` — решение
- `is_emergency boolean NOT NULL DEFAULT false`
- `priority_code varchar(20) NOT NULL` — low, normal, high, critical
- `current_status_id bigint NOT NULL` → `request_mgmt.work_order_status_ref`
- `parent_work_order_id bigint NULL` → `request_mgmt.work_order`

**Даты жизненного цикла:**
- `created_at timestamptz NOT NULL`
- `assigned_at timestamptz NULL`
- `accepted_at timestamptz NULL`
- `in_progress_at timestamptz NULL`
- `resident_contacted_at timestamptz NULL`
- `localized_at timestamptz NULL`
- `completed_at timestamptz NULL`
- `closed_at timestamptz NULL`
- `cancelled_at timestamptz NULL`
- `reopened_at timestamptz NULL`
- `updated_at timestamptz NOT NULL`

**Индексы:**
- `company_id, created_at desc`
- `company_id, department_id, current_status_id, created_at desc`
- `responsible_user_id, current_status_id, created_at desc`
- `department_id, created_at desc WHERE responsible_user_id IS NULL`
- `parent_work_order_id`
- `object_id`
- `service_id`
- `route_id`
- `is_test`

**CHECK ограничения:**
- `parent_work_order_id IS NULL OR parent_work_order_id <> work_order_id`
- `creation_source IN ('bot_json', 'manual_operator', 'manual_employee', 'manual_chief_engineer', 'manual_director', 'manual_django_admin')`
- `priority_code IN ('low', 'normal', 'high', 'critical')`
- `closed_at IS NULL OR completed_at IS NOT NULL OR cancelled_at IS NOT NULL`
- `completed_at IS NULL OR resolution_text IS NOT NULL`

---

#### 2.1.3. sla_instance

**Назначение:** Экземпляр SLA для конкретной заявки

**Ключевые поля:**
- `sla_instance_id bigint PK`
- `work_order_id bigint NOT NULL UNIQUE` → `request_mgmt.work_order`
- `company_id bigint NOT NULL` → `nsi_company`
- `sla_policy_id bigint NOT NULL` → `request_mgmt.sla_policy`

**Таймеры (шаблон):**
- `*_due_at timestamptz NULL` — дедлайн
- `*_stopped_at timestamptz NULL` — фактическая остановка
- `*_state varchar(20) NOT NULL DEFAULT 'waiting'` — waiting, met, overdue, not_applicable

**Таймеры:**
- `executor_assignment_*` — назначение исполнителя
- `work_start_*` — взятие в работу
- `resident_contact_*` — контакт с заявителем
- `localization_*` — локализация аварии (not_applicable для неаварийных)
- `resolution_*` — выполнение
- `auto_close_*` — автозакрытие

**Индексы:**
- `company_id`
- Partial indexes: `*_due_at WHERE *_state = 'waiting'` для каждого таймера

---

#### 2.1.4. work_order_event_log

**Назначение:** Единый журнал событий заявки

**Ключевые поля:**
- `event_id bigint PK`
- `work_order_id bigint NOT NULL` → `request_mgmt.work_order`
- `company_id bigint NOT NULL` → `nsi_company`
- `department_id bigint NULL` → `request_mgmt.company_department`
- `event_type_code varchar(50) NOT NULL` — тип события
- `event_datetime timestamptz NOT NULL` — дата/время события
- `author_user_id bigint NULL` → `auth_user`
- `text_value text NULL` — текст/комментарий
- `event_payload_json jsonb NULL` — доп. нагрузка

**Изменения сущностей (old_*/new_*):**
- `old_status_id`, `new_status_id` → `request_mgmt.work_order_status_ref`
- `old_service_id`, `new_service_id` → `services_catalog`
- `old_object_id`, `new_object_id` → `service_objects`
- `old_responsible_user_id`, `new_responsible_user_id` → `auth_user`

- `is_visible_to_resident boolean NOT NULL DEFAULT false`

**Индексы:**
- `work_order_id, event_datetime desc`
- `company_id, department_id, event_datetime desc`
- `event_type_code, event_datetime desc`

---

#### 2.1.5. work_order_attachment

**Назначение:** Вложения заявки (фото, документы)

**Ключевые поля:**
- `attachment_id bigint PK`
- `work_order_id bigint NOT NULL` → `request_mgmt.work_order`
- `event_id bigint NULL` → `request_mgmt.work_order_event_log`
- `uploaded_at timestamptz NOT NULL`
- `uploaded_by_user_id bigint NULL` → `auth_user`
- `attachment_kind varchar(30) NOT NULL` — incoming_photo, result_photo, document, other
- `mime_type varchar(120) NOT NULL`
- `file_name varchar(255) NOT NULL`
- `file_size bigint NOT NULL`
- `file_data bytea NOT NULL` — содержимое файла
- `is_visible_to_resident boolean NOT NULL DEFAULT false`
- `sort_order integer NOT NULL DEFAULT 100`

**Индексы:**
- `work_order_id`
- `event_id`
- `attachment_kind`

---

#### 2.1.6. notification_outbox

**Назначение:** Очередь уведомлений (без реальной отправки в MVP)

**Ключевые поля:**
- `outbox_id bigint PK`
- `company_id bigint NOT NULL` → `nsi_company`
- `work_order_id bigint NOT NULL` → `request_mgmt.work_order`
- `recipient_user_id bigint NOT NULL` → `auth_user`
- `event_type_code varchar(50) NOT NULL`
- `payload_json jsonb NULL`
- `status_code varchar(20) NOT NULL DEFAULT 'not_sent'` — not_sent, processed, ignored
- `created_at timestamptz NOT NULL`
- `processed_at timestamptz NULL`

**Индексы:**
- `status_code, created_at`
- `recipient_user_id, status_code`
- `work_order_id`

**События MVP:**
- Просрочка назначения исполнителя
- Просрочка взятия в работу
- Просрочка контакта с заявителем
- Просрочка исполнения

---

### 2.2. Справочники

#### 2.2.1. route_ref

**Назначение:** Справочник типовых маршрутов

**Поля:**
- `route_id bigint PK`
- `route_code varchar(50) NOT NULL UNIQUE` — технический код
- `route_name varchar(150) NOT NULL`
- `description text NULL`
- `is_active boolean NOT NULL DEFAULT true`

---

#### 2.2.2. company_department

**Назначение:** Иерархический справочник подразделений компании

**Поля:**
- `department_id bigint PK`
- `company_id bigint NOT NULL` → `nsi_company`
- `parent_department_id bigint NULL` → `request_mgmt.company_department` (иерархия)
- `department_name varchar(150) NOT NULL`
- `department_code varchar(50) NOT NULL`
- `is_active boolean NOT NULL DEFAULT true`
- `sort_order integer NOT NULL DEFAULT 100`

**UNIQUE:**
- `(company_id, department_code)`
- `(company_id, parent_department_id, department_name)`

**CHECK:**
- `parent_department_id <> department_id`

---

#### 2.2.3. company_route_mapping

**Назначение:** Настройка маршрута в конкретной компании

**Поля:**
- `company_route_mapping_id bigint PK`
- `company_id bigint NOT NULL` → `nsi_company`
- `route_id bigint NOT NULL` → `request_mgmt.route_ref`
- `target_department_id bigint NOT NULL` → `request_mgmt.company_department`
- `is_active boolean NOT NULL DEFAULT true`

**Partial UNIQUE:**
- `(company_id, route_id) WHERE is_active = true`

---

#### 2.2.4. contractor_organization

**Назначение:** Справочник подрядных организаций

**Поля:**
- `contractor_organization_id bigint PK`
- `contractor_name varchar(200) NOT NULL`
- `tax_id varchar(20) NULL`
- `phone varchar(50) NULL`
- `email varchar(254) NULL`
- `address text NULL`
- `is_active boolean NOT NULL DEFAULT true`

**Partial UNIQUE:**
- `(tax_id) WHERE tax_id IS NOT NULL`

---

#### 2.2.5. user_company_membership

**Назначение:** Привязка пользователя к компании, подразделению и роли

**Поля:**
- `user_company_membership_id bigint PK`
- `user_id bigint NOT NULL` → `auth_user`
- `company_id bigint NOT NULL` → `nsi_company`
- `department_id bigint NOT NULL` → `request_mgmt.company_department`
- `role_code varchar(50) NOT NULL` — resident, uk_user, executor, chief_engineer, direktor_uk, contractor, django_admin
- `contractor_organization_id bigint NULL` → `request_mgmt.contractor_organization`
- `is_primary boolean NOT NULL DEFAULT false`
- `date_from date NOT NULL`
- `date_to date NULL`
- `is_active boolean NOT NULL DEFAULT true`

**UNIQUE:**
- `(user_id, company_id, department_id, role_code, date_from)`
- Partial: `(user_id) WHERE is_primary = true AND is_active = true AND date_to IS NULL`

**CHECK:**
- `date_to IS NULL OR date_to >= date_from`

---

#### 2.2.6. company_object_service_period

**Назначение:** Период обслуживания объекта компанией

**Поля:**
- `company_object_service_period_id bigint PK`
- `company_id bigint NOT NULL` → `nsi_company`
- `object_id bigint NOT NULL` → `service_objects`
- `date_from date NOT NULL`
- `date_to date NULL` — NULL = открытый период
- `comment text NULL`
- `is_active boolean NOT NULL DEFAULT true`

**Exclusion constraint (пересечение периодов):**
- `object_id`
- `daterange(date_from, coalesce(date_to, 'infinity'::date), '[]')`
- Оператор: `&&` (пересечение)

**CHECK:**
- `date_to IS NULL OR date_to >= date_from`

---

#### 2.2.7. work_order_status_ref

**Назначение:** Справочник статусов заявки (единый для внутреннего и внешнего контуров)

**Поля:**
- `status_id bigint PK`
- `short_code_en varchar(50) NOT NULL UNIQUE` — технический код
- `short_name_ru varchar(100) NOT NULL` — название
- `display_name_for_user varchar(100) NOT NULL` — отображаемое название для пользователя
- `description_and_transition_rules text NULL` — описание бизнес-правил
- `sort_order integer NOT NULL DEFAULT 100` — порядок сортировки в UI
- `is_terminal boolean NOT NULL DEFAULT false` — конечный статус (нет переходов дальше)
- `is_active boolean NOT NULL DEFAULT true`

**Стартовые коды:**
- new_registered — Новая
- accepted_by_executor — Принята исполнителем
- in_progress — В работе
- on_hold — Приостановлена
- completed — Выполнена (терминальный)
- closed — Закрыта (терминальный)
- cancelled — Отменена (терминальный)
- reopened — Переоткрыта

---

#### 2.2.8. work_order_status_transition

**Назначение:** Допустимые переходы статусов

**Поля:**
- `transition_id bigint PK`
- `from_status_id bigint NOT NULL` → `request_mgmt.work_order_status_ref`
- `to_status_id bigint NOT NULL` → `request_mgmt.work_order_status_ref`
- `allowed_role_code varchar(50) NULL` — роль, которой разрешен переход
- `is_system_transition boolean NOT NULL DEFAULT false`
- `require_comment boolean NOT NULL DEFAULT false`
- `require_reason_code boolean NOT NULL DEFAULT false`
- `require_resolution_text boolean NOT NULL DEFAULT false`
- `require_result_photo boolean NOT NULL DEFAULT false`
- `require_executor_assigned boolean NOT NULL DEFAULT false`
- `is_active boolean NOT NULL DEFAULT true`

**UNIQUE:**
- `(from_status_id, to_status_id, allowed_role_code, is_system_transition)`

**CHECK:**
- `from_status_id <> to_status_id`

---

#### 2.2.9. sla_policy

**Назначение:** SLA-политики по услуге и приоритету

**Поля:**
- `sla_policy_id bigint PK`
- `company_id bigint NOT NULL` → `nsi_company`
- `service_id bigint NOT NULL` → `services_catalog`
- `is_emergency boolean NOT NULL DEFAULT false`
- `priority_code varchar(20) NOT NULL`
- `calendar_type varchar(20) NOT NULL` — 24x7, company_working_hours
- `executor_assignment_minutes integer NOT NULL`
- `work_start_minutes integer NOT NULL`
- `resident_contact_minutes integer NOT NULL`
- `localization_minutes integer NULL` — NULL для неаварийных
- `resolution_minutes integer NOT NULL`
- `auto_close_after_days integer NOT NULL`
- `policy_source varchar(20) NOT NULL` — normative, company, mixed
- `is_active boolean NOT NULL DEFAULT true`

**UNIQUE:**
- `(company_id, service_id, priority_code, is_emergency)`

**CHECK:**
- `calendar_type IN ('24x7', 'company_working_hours')`
- `policy_source IN ('normative', 'company', 'mixed')`
- Все числовые поля >= 0
- `localization_minutes IS NULL OR localization_minutes >= 0`
- Для `is_emergency = true`: `localization_minutes IS NOT NULL`

---

## 3. БИЗНЕС-ОГРАНИЧЕНИЯ

### 3.1. При создании work_order

1. **Проверка обслуживания объекта:**
   - `object_id` должен обслуживаться `company_id` на дату создания
   - Проверка через `request_mgmt.company_object_service_period`

2. **Определение маршрута и подразделения:**
   - `route_id` определяется по `service_id`
   - `department_id` определяется через активный `request_mgmt.company_route_mapping`
   - Сохранение без корректного `department_id` запрещено

3. **Обязательные поля:**
   - `company_id`, `object_id`, `service_id`, `route_id`, `department_id`
   - `creation_source`, `original_request_text`
   - `current_status_id`, `priority_code`

### 3.2. Назначение исполнителя

1. **Самоназначение:**
   - Разрешено только если заявка в подразделении пользователя
   - `responsible_user_id IS NULL`
   - Операция транзакционная: `select_for_update()`

2. **Переназначение:**
   - Разрешено только ролям: `chief_engineer`, `direktor_uk`, `django_admin`

### 3.3. Изменение статусов

1. **Перевод в completed:**
   - Запрещен при пустом `resolution_text`

2. **Переоткрытие:**
   - Разрешено из терминальных статусов согласно переходам

### 3.4. Редактирование полей

1. **original_request_text:**
   - Разрешено изменять только ролям `direktor_uk` и `django_admin`

2. **additional_info_text:**
   - Не должно быть доступно для редактирования жителю

### 3.5. История событий

При каждом значимом изменении `work_order` создавать запись в `work_order_event_log`:
- Создание, смена статуса, смена услуги, смена объекта, смена ответственного
- Доп. информация, контакт с заявителем, локализация, выполнение, закрытие, отмена, переоткрытие
- Автоматическая просрочка SLA

---

## 4. МЕХАНИЗМ СОЗДАНИЯ ЗАЯВКИ ИЗ INTAKE

### 4.1. Прикладной сервис

**Название:** `create_work_order_from_intake(request_intake_id)`

**Логика:**
1. Прочитать `request_intake`
2. Валидировать обязательные данные
3. Определить маршрут по услуге
4. Определить подразделение через активный `company_route_mapping`
5. Проверить обслуживание объекта компанией
6. Создать `work_order`
7. Создать `sla_instance`
8. Создать запись в `work_order_event_log`
9. Все в одной транзакции

**Если данных недостаточно:**
- `request_intake` сохраняется
- `work_order` не создается
- Причина фиксируется в логах

---

## 5. РАЗДЕЛЕНИЕ ДАННЫХ ПО КОМПАНИЯМ

Разделение обеспечивается на уровне:
1. **Модели данных:** поле `company_id` в основных сущностях
2. **Queryset:** фильтрация по `company_id`
3. **Service layer:** проверки принадлежности
4. **Form/view/admin:** валидации и ограничения доступа

**PostgreSQL RLS в этой фазе НЕ внедряется.**

---

## 6. ВНЕШНИЕ СУЩНОСТИ ДЛЯ FK

Согласно ТЗ, используются существующие таблицы проекта:

| Сущность в ТЗ | Фактическая таблица БД | Django модель |
|---|---|---|
| auth_user | auth_user | django.contrib.auth.models.User |
| nsi.Company | nsi_company | nsi.models.Company |
| portal.ServicesCatalog | services_catalog | portal.models.ServicesCatalog |
| Внутренний справочник объектов обслуживания | service_objects | (будет создана unmanaged модель) |

---

## 7. ТРЕБОВАНИЯ К UI

### 7.1. Экран исполнителя

- Две закладки: "Мои заявки" и "Пул подразделения"
- Нераспределенные заявки подсвечиваются розовым фоном
- Действия: "Открыть", "Взять на себя"

### 7.2. Карточка заявки сотрудника

- Полная информация: номер, компания, объект, услуга, маршрут, подразделение, ответственный
- Тексты: исходный текст, доп. сведения, решение
- Статус: единый (используется display_name_for_user для отображения)
- SLA-блок
- Журнал событий
- Вложения
- Дочерние/родительские заявки
- Кнопки допустимых действий

### 7.3. Форма ручного создания заявки

- Автоматическое определение маршрута и подразделения
- Валидация обязательных реквизитов

### 7.4. Управленческий список заявок

- Для директора и главного инженера
- Фильтры: компания, подразделение, статус, исполнитель, аварийность, просрочка SLA
- Действия: открыть, переназначить, закрыть, посмотреть просрочки

### 7.5. Экран жителя

- Список заявок жителя
- Карточка заявки: статус (display_name_for_user), текст, решение, видимые вложения
- Действие переоткрытия (если разрешено)

### 7.6. Django admin / Jazzmin

- Все сущности зарегистрированы
- Справочники и документы доступны для настройки и просмотра

---

## 8. SEED-КОМАНДА

**Название:** `seed_demo_work_orders --reset`

**Функционал:**
- Создает демонстрационные данные только с `is_test = true`
- `--reset`: безопасно очищает только тестовые данные
- Не затрагивает реальные данные
- Повторно запускаемая без ручных правок
- Полностью наполняет стенд для демонстрации всех интерфейсов

**Демонстрационные данные:**
1. 2 компании с оргструктурой и пользователями
2. 3 внешние подрядные организации
3. Маршруты и маппинги
4. Объекты обслуживания и периоды
5. SLA-политики
6. 20-30 тестовых заявок полного жизненного цикла
7. Статусы, переходы, события, вложения, уведомления

**Пароли всех тестовых пользователей:** `1`

---

## 9. КРИТЕРИИ ПРИЕМКИ

1. Все таблицы созданы в schema `request_mgmt`
2. Все PK, FK, unique, индексы, ограничения созданы
3. Во всех таблицах есть `is_test boolean NOT NULL DEFAULT false`
4. Backup БД создан
5. Архитектурный markdown создан
6. App `work_orders` создан с моделями и миграциями
7. Admin-регистрация выполнена
8. Seed-команда работает
9. Все интерфейсы реализованы и кликабельны
10. Self-check выполнен

---

## 10. ЗАПРЕТЫ ЭТОЙ ФАЗЫ

- Не создавать `request_case`
- Не использовать `UserFile` для вложений
- Не внедрять Celery/Redis/WebSocket
- Не внедрять PostgreSQL RLS
- Не делать отдельные сущности: `service_schema`, `service_routing_rule`, `escalation_rule`

---

**Конец документа**
