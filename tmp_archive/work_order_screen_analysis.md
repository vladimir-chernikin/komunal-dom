# Work Order Screen Analysis Report
## Проект: komunal-dom.ru (Django ЖКХ)
**Дата анализа:** 2026-03-28
**Аналитик:** Claude (Senior Django Analyst + UI Contract Extractor)
**Статус:** АНАЛИЗ БЕЗ ИЗМЕНЕНИЯ КОДА

---

# SUMMARY (Краткое резюме - 20 пунктов)

1. **ДВОЙНАЯ РЕАЛИЗАЦИЯ**: экран work_order существует в 2 видах - Django Admin (для администраторов) и Custom Web UI (для исполнителей/жителей)

2. **DJANGO ADMIN**: WorkOrderAdmin с 6 fieldsets точно соответствует указанным 6 вкладкам

3. **ОСНОВНАЯ МОДЕЛЬ**: WorkOrder (550 строк в models.py) - 35+ полей, 14 FK, 11 datetime, 2 TextField

4. **ФИКСИРОВАННЫЕ ВКЛАДКИ**: 6 fieldsets в admin.py: Основная информация, Текущее состояние, Текст заявки, Связи, Жизненный цикл, Служебное

5. **CUSTOM UI**: DetailView (work_order_detail.html) показывает УСЕЧЕННУЮ версию полей (15-20 полей вместо 35+)

6. **NET FORMS.PY**: отдельного файла forms.py НЕТ, используется ModelForm из Django CreateView

7. **ACTIONS**: 4 API endpoints (take, start, complete, close) + 2 упомянутых но не реализованных (pause, resume)

8. **READONLY FIELDS**: created_at, updated_at - системные, не редактируемые

9. **FK FIELDS**: 14 внешних ключей (company, object, service, route, department, responsible_user, request_intake, resident_user, parent_work_order, completed_by_user, closed_by_user, cancelled_by_user, current_internal_status, current_external_status)

10. **LIFECYCLE DATES**: 9 дат (created_at, assigned_at, accepted_at, in_progress_at, resident_contacted_at, localized_at, completed_at, closed_at, cancelled_at, reopened_at)

11. **CHOICE FIELDS**: priority_code (4 значения), creation_source (6 значений), is_emergency (bool)

12. **INLINES**: в admin.py НЕ используются, но есть связанные модели (WorkOrderEventLog, WorkOrderAttachment, SLAInstance, NotificationOutbox)

13. **AUTOCOMPLETE**: 11 FK полей используют autocomplete_fields в admin

14. **TEMPLATE ENGINE**: Django Templates + Bootstrap 5 + Bootstrap Icons

15. **JAVASCRIPT**: inline в templates для AJAX действий (take, start, complete), нет отдельных .js файлов

16. **CSS**: inline в base.html, нет отдельных .css файлов

17. **PERMISSIONS**: на уровне template checks ({% if work_order.responsible_user == user %}), RBAC через UserCompanyMembership

18. **VALIDATION**: на уровне Django model constraints (5 CheckConstraints), на уровне API views

19. **LOGGING**: WorkOrderEventLog для аудита всех действий

20. **RISK**: custom UI (work_order_detail.html) показывает НЕ ВСЕ поля из admin, возможны расхождения в бизнес-логике

---

# A. КАРТА РЕАЛИЗАЦИИ ЭКРАНА

| Файл | Роль файла | Что связано с work_order |
|------|------------|-------------------------|
| **work_orders/models.py** | Модель данных | WorkOrder (550 строк) - главная сущность с 35+ полями |
| **work_orders/admin.py** | Django Admin | WorkOrderAdmin с 6 fieldsets (точное соответствие 6 вкладкам) |
| **work_orders/views.py** | Контроллеры | WorkOrderDetailView (детальная карточка), WorkOrderCreateView (создание), 4 API endpoints |
| **work_orders/urls.py** | Маршрутизация | /work_orders/request/<id>/ (детальная), /work_orders/create/ (создание), /work_orders/api/<id>/<action>/ (действия) |
| **work_orders/templates/work_orders/work_order_detail.html** | Детальный экран | Custom UI с усеченным набором полей (15-20 полей) |
| **work_orders/templates/work_orders/work_order_create.html** | Форма создания | ModelForm с 5 полями (object, service, original_request_text, priority_code, is_emergency) |
| **work_orders/templates/work_orders/base.html** | Базовый шаблон | Bootstrap 5 + навигация |
| **Отсутствует** | forms.py | НЕТ отдельного файла, используется встроенный ModelForm из CreateView |
| **Отсутствует** | serializers.py | НЕТ, нет REST API |
| **Отсутствует** | presenters.py | НЕТ, логика в views.py |
| **Отсутствует** | **.js файлы** | НЕТ, JavaScript inline в templates |
| **Отсутствует** | **.css файлы** | НЕТ, CSS inline в base.html |

**Надежность вывода**: EXACT (проверено чтением файлов)

---

# B. ЭКРАН КАК ПОЛЬЗОВАТЕЛЬСКАЯ ФОРМА

## Сценарий 1: DJANGO ADMIN (полный набор полей)

### Вкладка 1: ОСНОВНАЯ ИНФОРМАЦИЯ
**Группа реквизитов**: Основная информация

| Поле | Тип | Источник значения | Editable | Readonly | Computed | Примечание |
|------|-----|-------------------|----------|----------|----------|------------|
| work_order_no | text (CharField) | user input/editable | YES | NO | NO | Уникальный номер заявки |
| company | fk (→ nsi.Company) | autocomplete | YES | NO | NO | Компания |
| object | fk (→ portal.ServiceObject) | autocomplete | YES | NO | NO | Объект обслуживания |
| service | fk (→ portal.ServicesCatalog) | autocomplete | YES | NO | NO | Услуга |
| route | fk (→ RouteRef) | autocomplete | YES | NO | NO | Маршрут |
| department | fk (→ CompanyDepartment) | autocomplete | YES | NO | NO | Подразделение |
| responsible_user | fk (→ User) | autocomplete | YES | NO | NO | Ответственный исполнитель |

**Надежность**: EXACT (из admin.py lines 109-110)

---

### Вкладка 2: ТЕКУЩЕЕ СОСТОЯНИЕ
**Группа реквизитов**: Текущее состояние

| Поле | Тип | Источник значения | Editable | Readonly | Computed | Примечание |
|------|-----|-------------------|----------|----------|----------|------------|
| current_internal_status | fk (→ WorkOrderStatusRef) | system/business logic | YES | NO | NO | Внутренний статус |
| current_external_status | fk (→ WorkOrderStatusRef) | system/business logic | YES | NO | NO | Внешний статус |
| priority_code | select (choices: 4) | user input/editable | YES | NO | NO | low/normal/high/critical |
| is_emergency | bool | user input/editable | YES | NO | NO | Аварийная заявка |

**Надежность**: EXACT (из admin.py lines 112-113)

---

### Вкладка 3: ТЕКСТ ЗАЯВКИ
**Группа реквизитов**: Текст заявки

| Поле | Тип | Источник значения | Editable | Readonly | Computed | Примечание |
|------|-----|-------------------|----------|----------|----------|------------|
| original_request_text | textarea (TextField) | user input/bot | YES | NO | NO | Исходный текст обращения |
| additional_info_text | textarea (TextField) | user input/editable | YES | NO | NO | Дополнительные сведения |
| resolution_text | textarea (TextField) | user input/editable | YES | NO | NO | Решение |

**Надежность**: EXACT (из admin.py lines 115-116)

---

### Вкладка 4: СВЯЗИ
**Группа реквизитов**: Связи

| Поле | Тип | Источник значения | Editable | Readonly | Computed | Примечание |
|------|-----|-------------------|----------|----------|----------|------------|
| request_intake | fk (→ RequestIntake) | system (bot JSON) | YES | NO | NO | OneToOne на входящее событие |
| resident_user | fk (→ User) | system (auth) | YES | NO | NO | Авторизованный житель |
| parent_work_order | fk (→ WorkOrder self) | user input/editable | YES | NO | NO | Родительская заявка |

**Надежность**: EXACT (из admin.py lines 118-119)

---

### Вкладка 5: ЖИЗНЕННЫЙ ЦИКЛ
**Группа реквизитов**: Жизненный цикл

| Поле | Тип | Источник значения | Editable | Readonly | Computed | Примечание |
|------|-----|-------------------|----------|----------|----------|------------|
| creation_source | select (choices: 6) | system/auto | YES | NO | NO | bot_json/manual_operator/... |
| created_at | datetime | system/auto_now_add | NO | YES | YES | Автоматически при создании |
| assigned_at | datetime | system/API | YES | NO | NO | Назначен |
| accepted_at | datetime | system/API | YES | NO | NO | Взят в работу |
| in_progress_at | datetime | system/API | YES | NO | NO | В работе |
| resident_contacted_at | datetime | system/API | YES | NO | NO | Контакт с заявителем |
| localized_at | datetime | system/API | YES | NO | NO | Локализовано |
| completed_at | datetime | system/API | YES | NO | NO | Выполнен |
| closed_at | datetime | system/API | YES | NO | NO | Закрыт |
| cancelled_at | datetime | system/API | YES | NO | NO | Отменен |
| reopened_at | datetime | system/API | YES | NO | NO | Переоткрыт |

**Надежность**: EXACT (из admin.py lines 121-123, models.py lines 691-700)

---

### Вкладка 6: СЛУЖЕБНОЕ
**Группа реквизитов**: Служебное (collapse - свернуто по умолчанию)

| Поле | Тип | Источник значения | Editable | Readonly | Computed | Примечание |
|------|-----|-------------------|----------|----------|----------|------------|
| message_log_ref | text | system (bot) | YES | NO | NO | Ссылка на MessageLog |
| completed_by_user | fk (→ User) | system/API | YES | NO | NO | Выполнено пользователем |
| closed_by_user | fk (→ User) | system/API | YES | NO | NO | Закрыто пользователем |
| cancelled_by_user | fk (→ User) | system/API | YES | NO | NO | Отменено пользователем |
| updated_at | datetime | system/auto_now | NO | YES | YES | Автоматически при обновлении |
| is_test | bool | system/manual | YES | NO | NO | Тестовый (NOT NULL DEFAULT false) |

**Надежность**: EXACT (из admin.py lines 125-128)

---

## Сценарий 2: CUSTOM WEB UI (усеченный набор полей)

### Work Order Detail View (work_order_detail.html)

**Отображаемые поля** (примерно 15-20 из 35+):

| Поле | Отображается | Примечание |
|------|--------------|------------|
| work_order_no | YES | В заголовке карточки |
| is_emergency | YES | Бейдж "АВАРИЯ" |
| priority_code | YES | Бейдж с приоритетом |
| current_internal_status | YES | Badge bg-primary |
| current_external_status | YES | Badge bg-info |
| original_request_text | YES | Описание заявки |
| additional_info_text | YES | Маленький текст (если есть) |
| resolution_text | YES | Alert alert-success (если есть) |
| service.scenario_name | YES | Услуга |
| object.service_object_id | YES | Объект #ID |
| department.department_name | YES | Подразделение |
| responsible_user | YES | Исполнитель (или "Не назначен") |
| created_at | YES | Создана |
| assigned_at | YES | Если есть значение |
| in_progress_at | YES | Если есть значение |
| completed_at | YES | Если есть значение |
| **ОТСУТСТВУЕТ** | NO | company |
| **ОТСУТСТВУЕТ** | NO | route |
| **ОТСУТСТВУЕТ** | NO | request_intake |
| **ОТСУТСТВУЕТ** | NO | resident_user |
| **ОТСУТСТВУЕТ** | NO | parent_work_order |
| **ОТСУТСТВУЕТ** | NO | creation_source |
| **ОТСУТСТВУЕТ** | NO | accepted_at, resident_contacted_at, localized_at, closed_at, cancelled_at, reopened_at |
| **ОТСУТСТВУЕТ** | NO | message_log_ref, completed_by_user, closed_by_user, cancelled_by_user |
| **ОТСУТСТВУЕТ** | NO | updated_at |
| **ОТСУТСТВУЕТ** | NO | is_test |

**Надежность**: EXACT (проверено чтением work_order_detail.html, lines 37-126)

---

### Work Order Create View (work_order_create.html)

**Поля формы** (5 полей):

| Поле | Тип | Обязательность | Виджет |
|------|-----|----------------|--------|
| object | fk (→ portal.ServiceObject) | REQUIRED | select (form-select) |
| service | fk (→ portal.ServicesCatalog) | REQUIRED | select (form-select) |
| original_request_text | textarea (TextField) | REQUIRED | textarea (form-control) |
| priority_code | select (choices: 4) | OPTIONAL | select (form-select) |
| is_emergency | bool | OPTIONAL | checkbox |

**Надежность**: EXACT (из views.py line 160, work_order_create.html lines 27-75)

---

# C. ДЕЙСТВИЯ ФОРМЫ (ACTIONS)

| Action code | Label | Где определено | Условие доступности | Предполагаемый смысл |
|-------------|-------|----------------|---------------------|---------------------|
| **take_work_order** | "Взять заявку в работу" | views.py line 289, template line 164 | responsible_user is None AND user has membership in department | Назначить текущего пользователя исполнителем |
| **start_work_order** | "Начать выполнение" | views.py line 333, template line 138 | responsible_user == current user AND status == 'accepted_by_executor' | Перевести в статус "В работе" |
| **complete_work_order** | "Завершить выполнение" | views.py line 366, template line 144 | responsible_user == current user AND status == 'in_progress' AND resolution_text required | Перевести в статус "Выполнена" |
| **close_work_order** | "Закрыть заявку" | views.py line 407 | role_code in ['direktor_uk', 'chief_engineer'] AND completed_at is not null | Перевести в статус "Закрыта" |
| **pause_work_order** | "Приостановить" | template line 147 (button exists) | mentioned in template, NO backend implementation | **НЕ РЕАЛИЗОВАНО** |
| **resume_work_order** | "Возобновить" | template line 153 (button exists) | mentioned in template, NO backend implementation | **НЕ РЕАЛИЗОВАНО** |
| **create_work_order** | "Создать заявку" | views.py line 156, CreateView | user has active membership | Ручное создание заявки сотрудником |

**Надежность**: EXACT (для реализованных), INFERRED (для pause/resume - только в template)

---

# D. ПРАВИЛА И ЗАВИСИМОСТИ

## Правила видимости (visible_when)

| Объект | Тип правила | Условие | Где найдено | Надежность |
|--------|-------------|---------|-------------|------------|
| completeModal (modal) | visible_when | current_internal_status == 'in_progress' AND responsible_user == current_user | work_order_detail.html line 143 | EXACT |
| startWorkOrder button | visible_when | current_internal_status == 'accepted_by_executor' AND responsible_user == current_user | work_order_detail.html line 137 | EXACT |
| pauseWorkOrder button | visible_when | current_internal_status == 'in_progress' AND responsible_user == current_user | work_order_detail.html line 147 | EXACT (но backend нет) |
| resumeWorkOrder button | visible_when | current_internal_status == 'on_hold' AND responsible_user == current_user | work_order_detail.html line 152 | EXACT (но backend нет) |
| takeWorkOrder button | visible_when | responsible_user is None | work_order_detail.html line 161 | EXACT |
| Actions card | visible_when | responsible_user == current_user | work_order_detail.html line 131 | EXACT |
| assigned_at, in_progress_at, completed_at | visible_when | field is not null | work_order_detail.html lines 108-125 | EXACT |

---

## Правила обязательности (required_when)

| Объект | Тип правила | Условие | Где найдено | Надежность |
|--------|-------------|---------|-------------|------------|
| resolution_text | required_when | action == 'complete_work_order' | views.py line 378 (validation) | EXACT |
| object, service, original_request_text | required_when | action == 'create_work_order' | views.py line 160 (fields list) | EXACT |

---

## Правила readonly (readonly_when)

| Объект | Тип правила | Условие | Где найдено | Надежность |
|--------|-------------|---------|-------------|------------|
| created_at, updated_at | readonly_when | ALWAYS (system fields) | admin.py line 139 (readonly_fields) | EXACT |
| request_intake.received_at, created_at, updated_at | readonly_when | ALWAYS | admin.py line 102 (readonly_fields) | EXACT |
| WorkOrderEventLog.event_datetime, created_at, updated_at | readonly_when | ALWAYS | admin.py line 173 (readonly_fields) | EXACT |
| WorkOrderAttachment.uploaded_at, created_at, updated_at | readonly_when | ALWAYS | admin.py line 186 (readonly_fields) | EXACT |
| NotificationOutbox.created_at, processed_at, updated_at | readonly_when | ALWAYS | admin.py line 197 (readonly_fields) | EXACT |

---

## Правила разрешений (permission_guard)

| Объект | Тип правила | Условие | Где найдено | Надежность |
|--------|-------------|---------|-------------|------------|
| take_work_order | permission_guard | user.is_authenticated AND user has membership in work_order.department | views.py lines 301-308 | EXACT |
| start_work_order | permission_guard | work_order.responsible_user == request.user | views.py line 341 | EXACT |
| complete_work_order | permission_guard | work_order.responsible_user == request.user | views.py line 374 | EXACT |
| close_work_order | permission_guard | role_code in ['direktor_uk', 'chief_engineer'] | views.py lines 415-420 | EXACT |
| WorkOrderDetailView | permission_guard | LoginRequiredMixin | views.py line 134 | EXACT |
| ManagementListView | permission_guard | role_code in ['direktor_uk', 'chief_engineer'] | views.py lines 220-221 | EXACT |

---

## Вычисляемые поля (computed_from)

| Объект | Тип правила | Условие | Где найдено | Надежность |
|--------|-------------|---------|-------------|------------|
| created_at | computed_from | auto_now_add=True | models.py line 691 | EXACT |
| updated_at | computed_from | auto_now=True | models.py line 701 | EXACT |
| current_internal_status | computed_from | Business logic transitions (not auto) | views.py, API | INFERRED |
| current_external_status | computed_from | Business logic transitions (not auto) | views.py, API | INFERRED |

---

## Бизнес-правила (business_rules)

| Объект | Тип правила | Условие | Где найдено | Надежность |
|--------|-------------|---------|-------------|------------|
| parent_work_order | check_constraint | parent_work_order__isnull=True OR parent_work_order != id | models.py lines 710-712 | EXACT |
| priority_code | check_constraint | priority_code in ['low', 'normal', 'high', 'critical'] | models.py lines 722-724 | EXACT |
| closed_at | check_constraint | closed_at__isnull=True OR completed_at__isnull=False OR cancelled_at__isnull=False | models.py lines 726-728 | EXACT |
| completed_at | check_constraint | completed_at__isnull=True OR resolution_text__isnull=False | models.py lines 730-732 | EXACT |
| is_test | default_value | DEFAULT false (NOT NULL) | models.py line 702 | EXACT |

---

# E. ЧЕРНОВИК ИСТОЧНИКОВ ИСТИНЫ

## ДОЛЖНО ЖИТЬ В METADATA

**Справочники и lookup данные:**
- ✅ WorkOrderStatusRef (статусы заявки)
- ✅ WorkOrderStatusTransition (допустимые переходы)
- ✅ RouteRef (типовые маршруты)
- ✅ CompanyDepartment (подразделения)
- ✅ SLAPolicy (SLA политики)

**Метаданные полей:**
- ✅ CHOICE определения: priority_code (4 значения), creation_source (6 значений), PRIORITY_CHOICES, CALENDAR_TYPE_CHOICES, STATUS_SCOPE_CHOICES
- ✅ TextField длина и валидация: original_request_text, additional_info_text, resolution_text
- ✅ DateTime поля жизненного цикла: 11 дат
- ✅ FK связи: 14 внешних ключей

**Правила валидации:**
- ✅ CheckConstraints из models.py
- ✅ Required_when правила
- ✅ UniqueConstraints

**Разметка экрана:**
- ✅ 6 fieldsets (admin.py) - можно использовать как исходную структуру вкладок
- ✅ collapse/expanded состояния
- ✅ Порядок полей внутри fieldsets

---

## ДОЛЖНО ЖИТЬ В FIGMA

**Layout и визуальная иерархия:**
- ✅ 6 вкладок (fieldsets)
- ✅ Карточная форма (Bootstrap card-based layout)
- ✅ Grid layout (2 колонки для деталей, 1 колонка для timeline)
- ✅ Расположение actions (кнопок) относительно полей
- ✅ Modal для завершения заявки

**Визуальные состояния:**
- ✅ Emergency badge (пульсирующая анимация)
- ✅ Status badges (color-coded: primary, info, danger)
- ✅ Priority badge
- �** Timeline/history layout (правая колонка)

**Typography и spacing:**
- ✅ Заголовки h5, h6
- ✅ Text-muted для лейблов
- ✅ Badge размеры
- �** Карточные отступы

**Компоненты:**
- ✅ Кнопки действий (start, complete, pause, resume)
- ✅ Modal completeWorkOrder
- �** Timeline компонент
- ✅ Breadcrumb навигация

---

## ДОЛЖНО ЖИТЬ В DJANGO CODE

**Бизнес-логика:**
- ✅ API endpoints (take, start, complete, close)
- ✅ Status transition logic
- ✅ SLA calculation (если есть)
- ✅ Permission checks (RBAC через UserCompanyMembership)
- ✅ Event logging (WorkOrderEventLog)

**Data access layer:**
- ✅ Model definitions (WorkOrder, related models)
- �** QuerySets (select_related optimization)
- ✅** Database indexes

**Server-side validation:**
- ✅ View-level validation (resolution_text required)
- ✅ Permission guards
- ✅ CSRF protection

**Интеграция:**
- ✅ MessageLog integration (message_log_ref)
- ✅ Notification outbox
- ✅** RequestIntake integration
- ✅** Bot integration (bot_json source)

---

## НЕОПРЕДЕЛЕННОСТЬ:

| Артефакт | Текущее расположение | Рекомендуемое | Комментарий |
|----------|---------------------|---------------|-------------|
| Валидация формы создания (5 полей) | views.py (inline) | Metadata или Code | Простая форма, можно оставить в Code |
| Определение 6 вкладок | admin.py (hardcoded) | Metadata | Перенести в YAML metadata |
| Порядок полей во вкладках | admin.py (hardcoded) | Metadata | Перенести в YAML metadata |
| visible_when правила | template (inline JS) | Metadata | Вынести в metadata-driven UI |
| required_when правила | views.py (hardcoded) | Metadata | Вынести в YAML metadata |
| Buttons actions (pause/resume) | template only (NO backend) | Code | Нужно добавить backend implementation |

---

# F. ЧЕРНОВИК FORM CONTRACT

```yaml
screen:
  code: "work_order_detail"
  name: "Заявка ЖКХ"
  description: "Карточка заявки с полным жизненным циклом"
  version: "1.0.0"
  implementation:
    - type: "django_admin"
      model: "work_orders.WorkOrder"
      admin_class: "WorkOrderAdmin"
      file: "work_orders/admin.py:106"
    - type: "custom_ui"
      view: "WorkOrderDetailView"
      template: "work_orders/work_order_detail.html"
      url: "/work_orders/request/<id>/"

model:
  app: "work_orders"
  name: "WorkOrder"
  table: "request_mgmt.work_order"
  primary_key: "id"
  display_field: "work_order_no"
  fields_count: 35
  fks_count: 14
  datetimes_count: 11

tabs:
  - code: "main_info"
    name: "Основная информация"
    order: 1
    collapsed: false
    groups:
      - code: "main"
        fields:
          - field: "work_order_no"
            type: "text"
            editable: true
            required: true
            unique: true
            max_length: 30
          - field: "company"
            type: "fk"
            editable: true
            required: true
            target_model: "nsi.Company"
            autocomplete: true
          - field: "object"
            type: "fk"
            editable: true
            required: true
            target_model: "portal.ServiceObject"
            autocomplete: true
          - field: "service"
            type: "fk"
            editable: true
            required: true
            target_model: "portal.ServicesCatalog"
            autocomplete: true
          - field: "route"
            type: "fk"
            editable: true
            required: true
            target_model: "work_orders.RouteRef"
            autocomplete: true
          - field: "department"
            type: "fk"
            editable: true
            required: true
            target_model: "work_orders.CompanyDepartment"
            autocomplete: true
          - field: "responsible_user"
            type: "fk"
            editable: true
            required: false
            target_model: "auth.User"
            autocomplete: true

  - code: "current_state"
    name: "Текущее состояние"
    order: 2
    collapsed: false
    groups:
      - code: "state"
        fields:
          - field: "current_internal_status"
            type: "fk"
            editable: true
            required: true
            target_model: "work_orders.WorkOrderStatusRef"
            filter: {"status_scope": "internal"}
          - field: "current_external_status"
            type: "fk"
            editable: true
            required: true
            target_model: "work_orders.WorkOrderStatusRef"
            filter: {"status_scope": "external"}
          - field: "priority_code"
            type: "select"
            editable: true
            required: true
            choices:
              - value: "low"
                label: "Низкий"
              - value: "normal"
                label: "Обычный"
              - value: "high"
                label: "Высокий"
              - value: "critical"
                label: "Критический"
            default: "normal"
          - field: "is_emergency"
            type: "bool"
            editable: true
            required: false
            default: false
            ui_hint: "emergency_badge"

  - code: "request_text"
    name: "Текст заявки"
    order: 3
    collapsed: false
    groups:
      - code: "text_fields"
        fields:
          - field: "original_request_text"
            type: "textarea"
            editable: true
            required: true
            rows: 5
            placeholder: "Опишите проблему подробно"
          - field: "additional_info_text"
            type: "textarea"
            editable: true
            required: false
            rows: 3
            placeholder: "Дополнительные сведения"
          - field: "resolution_text"
            type: "textarea"
            editable: true
            required_when: "status in ['completed', 'closed']"
            rows: 5
            placeholder: "Опишите, что было сделано"

  - code: "relations"
    name: "Связи"
    order: 4
    collapsed: false
    groups:
      - code: "links"
        fields:
          - field: "request_intake"
            type: "fk"
            editable: true
            required: false
            target_model: "work_orders.RequestIntake"
            readonly_source: "bot_json"
          - field: "resident_user"
            type: "fk"
            editable: true
            required: false
            target_model: "auth.User"
            autocomplete: true
          - field: "parent_work_order"
            type: "fk"
            editable: true
            required: false
            target_model: "work_orders.WorkOrder"
            autocomplete: true

  - code: "lifecycle"
    name: "Жизненный цикл"
    order: 5
    collapsed: false
    groups:
      - code: "dates"
        fields:
          - field: "creation_source"
            type: "select"
            editable: true
            required: true
            choices:
              - value: "bot_json"
                label: "Бот (JSON)"
              - value: "manual_operator"
                label: "Вручную оператором"
              - value: "manual_employee"
                label: "Вручную сотрудником"
              - value: "manual_chief_engineer"
                label: "Вручную главным инженером"
              - value: "manual_director"
                label: "Вручную директором"
              - value: "manual_django_admin"
                label: "Вручную Django-админом"
          - field: "created_at"
            type: "datetime"
            editable: false
            readonly: true
            computed: "auto_now_add"
          - field: "assigned_at"
            type: "datetime"
            editable: true
            required: false
          - field: "accepted_at"
            type: "datetime"
            editable: true
            required: false
          - field: "in_progress_at"
            type: "datetime"
            editable: true
            required: false
          - field: "resident_contacted_at"
            type: "datetime"
            editable: true
            required: false
          - field: "localized_at"
            type: "datetime"
            editable: true
            required: false
          - field: "completed_at"
            type: "datetime"
            editable: true
            required: false
          - field: "closed_at"
            type: "datetime"
            editable: true
            required: false
            validation: "requires completed_at or cancelled_at"
          - field: "cancelled_at"
            type: "datetime"
            editable: true
            required: false
          - field: "reopened_at"
            type: "datetime"
            editable: true
            required: false

  - code: "service"
    name: "Служебное"
    order: 6
    collapsed: true
    groups:
      - code: "system"
        fields:
          - field: "message_log_ref"
            type: "text"
            editable: true
            required: false
            max_length: 255
            system: true
          - field: "completed_by_user"
            type: "fk"
            editable: true
            required: false
            target_model: "auth.User"
            autocomplete: true
          - field: "closed_by_user"
            type: "fk"
            editable: true
            required: false
            target_model: "auth.User"
            autocomplete: true
          - field: "cancelled_by_user"
            type: "fk"
            editable: true
            required: false
            target_model: "auth.User"
            autocomplete: true
          - field: "updated_at"
            type: "datetime"
            editable: false
            readonly: true
            computed: "auto_now"
          - field: "is_test"
            type: "bool"
            editable: true
            required: true
            default: false
            system: true

actions:
  - code: "take_work_order"
    label: "Взять заявку в работу"
    icon: "bi-hand-index-thumb"
    type: "api"
    method: "POST"
    endpoint: "/work_orders/api/<id>/take/"
    permission_guard: "user.is_authenticated AND user.has_membership(department)"
    condition: "work_order.responsible_user is NULL"
    effects:
      - field: "responsible_user"
        value: "current_user"
      - field: "assigned_at"
        value: "now()"
      - field: "current_internal_status"
        value: "accepted_by_executor"
    side_effects:
      - create_event_log: "assigned"

  - code: "start_work_order"
    label: "Начать выполнение"
    icon: "bi-play-circle"
    type: "api"
    method: "POST"
    endpoint: "/work_orders/api/<id>/start/"
    permission_guard: "work_order.responsible_user == current_user"
    condition: "current_internal_status == 'accepted_by_executor'"
    effects:
      - field: "current_internal_status"
        value: "in_progress"
      - field: "in_progress_at"
        value: "now()"
    side_effects:
      - create_event_log: "status_changed"
      - notify_resident: true

  - code: "complete_work_order"
    label: "Завершить выполнение"
    icon: "bi-check-circle"
    type: "modal"
    modal_id: "completeModal"
    endpoint: "/work_orders/api/<id>/complete/"
    method: "POST"
    permission_guard: "work_order.responsible_user == current_user"
    condition: "current_internal_status == 'in_progress'"
    requires:
      - field: "resolution_text"
        required: true
        validation: "not blank"
    effects:
      - field: "current_internal_status"
        value: "completed"
      - field: "current_external_status"
        value: "completed_external"
      - field: "resolution_text"
        value: "user_input"
      - field: "completed_at"
        value: "now()"
      - field: "completed_by_user"
        value: "current_user"
    side_effects:
      - create_event_log: "completed"
      - notify_resident: true

  - code: "close_work_order"
    label: "Закрыть заявку"
    icon: "bi-x-circle"
    type: "api"
    method: "POST"
    endpoint: "/work_orders/api/<id>/close/"
    permission_guard: "role_code in ['direktor_uk', 'chief_engineer']"
    condition: "completed_at is not null"
    effects:
      - field: "current_internal_status"
        value: "closed"
      - field: "current_external_status"
        value: "closed_external"
      - field: "closed_at"
        value: "now()"
      - field: "closed_by_user"
        value: "current_user"
    side_effects:
      - create_event_log: "closed"
      - notify_resident: true

  - code: "pause_work_order"
    label: "Приостановить"
    icon: "bi-pause-circle"
    type: "api"
    method: "POST"
    endpoint: "/work_orders/api/<id>/pause/"
    permission_guard: "work_order.responsible_user == current_user"
    condition: "current_internal_status == 'in_progress'"
    status: "NOT_IMPLEMENTED"
    notes: "Button exists in template, but NO backend implementation"

  - code: "resume_work_order"
    label: "Возобновить"
    icon: "bi-play-circle"
    type: "api"
    method: "POST"
    endpoint: "/work_orders/api/<id>/resume/"
    permission_guard: "work_order.responsible_user == current_user"
    condition: "current_internal_status == 'on_hold'"
    status: "NOT_IMPLEMENTED"
    notes: "Button exists in template, but NO backend implementation"

  - code: "create_work_order"
    label: "Создать заявку"
    icon: "bi-plus-circle"
    type: "view"
    view: "WorkOrderCreateView"
    url: "/work_orders/create/"
    permission_guard: "user.has_active_membership()"
    fields:
      - field: "object"
        required: true
      - field: "service"
        required: true
      - field: "original_request_text"
        required: true
      - field: "priority_code"
        required: false
        default: "normal"
      - field: "is_emergency"
        required: false
        default: false

rules:
  - object: "parent_work_order"
    type: "check_constraint"
    rule: "parent_work_order is NULL OR parent_work_order != self.id"
    source: "models.py line 710"
    reliability: "exact"

  - object: "priority_code"
    type: "check_constraint"
    rule: "priority_code IN ['low', 'normal', 'high', 'critical']"
    source: "models.py line 722"
    reliability: "exact"

  - object: "closed_at"
    type: "check_constraint"
    rule: "closed_at is NULL OR (completed_at is NOT NULL OR cancelled_at is NOT NULL)"
    source: "models.py line 726"
    reliability: "exact"

  - object: "completed_at"
    type: "check_constraint"
    rule: "completed_at is NULL OR resolution_text is NOT NULL"
    source: "models.py line 730"
    reliability: "exact"

  - object: "created_at, updated_at"
    type: "readonly_when"
    rule: "ALWAYS (system fields)"
    source: "admin.py line 139"
    reliability: "exact"

  - object: "completeModal"
    type: "visible_when"
    rule: "current_internal_status == 'in_progress' AND responsible_user == current_user"
    source: "work_order_detail.html line 143"
    reliability: "exact"

  - object: "startWorkOrder button"
    type: "visible_when"
    rule: "current_internal_status == 'accepted_by_executor' AND responsible_user == current_user"
    source: "work_order_detail.html line 137"
    reliability: "exact"

  - object: "takeWorkOrder button"
    type: "visible_when"
    rule: "responsible_user is NULL"
    source: "work_order_detail.html line 161"
    reliability: "exact"

  - object: "resolution_text"
    type: "required_when"
    rule: "action == 'complete_work_order'"
    source: "views.py line 378"
    reliability: "exact"

  - object: "take_work_order action"
    type: "permission_guard"
    rule: "user.is_authenticated AND user.has_membership(work_order.department)"
    source: "views.py lines 301-308"
    reliability: "exact"

  - object: "start_work_order action"
    type: "permission_guard"
    rule: "work_order.responsible_user == request.user"
    source: "views.py line 341"
    reliability: "exact"

  - object: "complete_work_order action"
    type: "permission_guard"
    rule: "work_order.responsible_user == request.user"
    source: "views.py line 374"
    reliability: "exact"

  - object: "close_work_order action"
    type: "permission_guard"
    rule: "role_code IN ['direktor_uk', 'chief_engineer']"
    source: "views.py lines 415-420"
    reliability: "exact"

layout_hints:
  framework: "bootstrap_5"
  grid:
    main_columns: 2
    detail_sidebar: true
    sidebar_width: "col-lg-4"
    main_width: "col-lg-8"

  components:
    - type: "card"
      header: true
      body: true
      footer: false

    - type: "badge"
      emergency: "pulse_animation"
      status: "color_coded"

    - type: "modal"
      id: "completeModal"
      fields:
        - field: "resolution_text"
          widget: "textarea"
          rows: 5
          required: true

    - type: "timeline"
      position: "sidebar"
      source: "WorkOrderEventLog"
      order: "-event_datetime"
      display:
        - "event_datetime"
        - "author_user"
        - "text_value"
        - "new_status"

  navigation:
    - type: "breadcrumb"
      items:
        - label: "Дашборд"
          url: "/work_orders/executor/"
        - label: "{{ work_order_no }}"
          active: true

related_entities:
  - model: "WorkOrderEventLog"
    relation: "ForeignKey (work_order → events)"
    display: "timeline in sidebar"

  - model: "WorkOrderAttachment"
    relation: "ForeignKey (work_order → attachments)"
    display: "NOT SHOWN in current UI"

  - model: "SLAInstance"
    relation: "OneToOneField (work_order → sla)"
    display: "NOT SHOWN in current UI"

  - model: "NotificationOutbox"
    relation: "ForeignKey (work_order → notifications)"
    display: "NOT SHOWN in current UI"

metadata_source:
  extraction_method: "static_analysis"
  analyzed_files:
    - "work_orders/models.py"
    - "work_orders/admin.py"
    - "work_orders/views.py"
    - "work_orders/urls.py"
    - "work_orders/templates/work_orders/work_order_detail.html"
    - "work_orders/templates/work_orders/work_order_create.html"
    - "work_orders/templates/work_orders/base.html"

  extraction_date: "2026-03-28"
  reliability:
    admin_structure: "exact"
    custom_ui_structure: "exact"
    model_fields: "exact"
    actions: "exact (implemented), inferred (mentioned but not implemented)"
    rules: "exact (from code), inferred (from button visibility)"
```

---

# СПИСОК НЕЯСНОСТЕЙ

## Критические неясности

1. **РАСХОЖДЕНИЕ UI**: Django Admin показывает все 35+ полей, custom UI (work_order_detail.html) - только 15-20.
   - **Вопрос**: Какой UI является источником истины для пользователей?
   - **Риск**: Потеря данных при редактировании через custom UI

2. **НЕРАЕЛИЗОВАННЫЕ ACTIONS**: Кнопки pause/resume есть в template, но NO backend implementation.
   - **Вопрос**: Это баг или feature in progress?
   - **Риск**: Пользователь видит кнопку, но она не работает

3. **СТАТУС 'on_hold'**: Упомянут в template (line 152), но НЕТ в models.py STATUS_SCOPE_CHOICES.
   - **Вопрос**: Существует ли этот статус в БД?
   - **Риск**: Кнопка "Возобновить" никогда не покажется

4. **FORMS.PY**: Отдельного файла forms.py НЕТ, используется встроенный ModelForm.
   - **Вопрос**: Есть ли custom validation логика?
   - **Риск**: Недостаточно валидации для user-facing формы

## Средние неясности

5. **SLAInstance**: Связана OneToOne с WorkOrder, но НЕ отображается в UI.
   - **Вопрос**: Планируется ли показывать SLA таймеры?
   - **Риск**: Пользователи не видят дедлайны

6. **WorkOrderAttachment**: Есть модель и admin, но НЕТ в custom UI.
   - **Вопрос**: Как пользователи загружают фото?
   - **Риск**: Фото можно загрузить только через admin

7. **REQUEST_INTAKE INTEGRATION**: request_intake field есть в модели, но НЕ в custom UI.
   - **Вопрос**: Нужно ли показывать связь с исходным JSON?
   - **Риск**: Потеря контекста при обработке

8. **MESSAGE_LOG_REF**: Поле есть в модели и admin, но НЕ в custom UI.
   - **Вопрос**: Для чего это поле? Как просмотреть лог?
   - **Риск**: Сложно дебажить интеграцию с ботом

## Низкие неясности

9. **CREATION_SOURCE DISPLAY**: В admin есть поле creation_source с 6 вариантами, в custom UI НЕ отображается.
   - **Вопрос**: Нужно ли показывать источник создания?
   - **Риск**: Аналитика по каналам поступления

10. **PARENT_WORK_ORDER**: Поле есть, но НЕ в custom UI.
    - **Вопрос**: Используется ли связь родитель-потомок?
    - **Риск**: Сложно отслеживать связанные заявки

---

# ТЕХНИЧЕСКИЕ РИСКИ ДЛЯ ПЕРЕХОДА НА METADATA-DRIVEN UI

## Критические риски

1. **ДВОЙНАЯ ИМПЛЕМЕНТАЦИЯ**: Django Admin + Custom UI с разным набором полей
   - **Риск**: Непонятно, какой набор полей считать каноничным
   - **Mitigation**: Определить single source of truth BEFORE migration

2. **HARDCODED TEMPLATE LOGIC**: Вся логика видимости (visible_when) ЗАШИТА в template
   - **Пример**: `{% if work_order.responsible_user == user %}` (line 131)
   - **Риск**: Сложно extracted to metadata без переписывания template
   - **Mitigation**: Use template tags or component library

3. **INLINE JAVASCRIPT**: Вся AJAX логика inline в template (lines 227-294)
   - **Риск**: Сложно extracted to reusable components
   - **Mitigation**: Extract to separate .js files BEFORE migration

4. **NET FORMS.PY**: Отсутствие отдельного файла форм означает, что validation логика РАЗМАЗАНА
   - **Риск**: Часть validation в models.py, часть в views.py, часть в template
   - **Mitigation**: Consolidate validation logic BEFORE metadata extraction

## Средние риски

5. **BUTTONS WITHOUT BACKEND**: pause/resume упомянуты но не реализованы
   - **Риск**: Metadata будет описывать НЕСУЩЕСТВУЮЩУЮ функциональность
   - **Mitigation**: Implement or remove BEFORE metadata extraction

6. **AUTOCOMPLETE FIELDS**: 11 FK полей используют autocomplete_fields в admin
   - **Риск**: Custom UI НЕ использует autocomplete, просто select
   - **Mitigation**: Решить, нужна ли autocomplete для metadata-driven UI

7. **DATETIME FIELD HANDLING**: 11 datetime fields с conditional visibility
   - **Риск**: Сложно metadata-driven conditional visibility
   - **Mitigation**: Use robust rule engine (jsonpath / JSON logic)

8. **MODAL vs INLINE ACTIONS**: complete_work_order использует modal, другие - inline
   - **Риск**: Несогласованный UX pattern
   - **Mitigation**: Определить единый подход в metadata

## Низкие риски

9. **CSS INLINE**: Все стили inline в base.html
   - **Риск**: Сложно поддерживать theme consistency
   - **Mitigation**: Extract to component-scoped CSS

10. **NO SERIALIZERS.PY**: Отсутствие REST API serializers
    - **Риск**: Metadata-driven UI предполагает JSON API
    - **Mitigation**: Implement REST API BEFORE migration

11. **NO PRESENTERS/PREPARERS**: Логика подготовки данных РАЗМАЗАНА по views
    - **Риск**: Сложно extracted to metadata
    - **Mitigation**: Introduce presenter layer

12. **BOOTSTRAP 5 DEPENDENCY**: UI жестко привязан к Bootstrap 5
    - **Риск**: Сложно сменить UI framework
    - **Mitigation**: Use component abstraction layer

---

# МИНИМАЛЬНЫЙ НАБОР ФАЙЛОВ ДЛЯ ДАЛЬНЕЙШЕГО ПРОЕКТИРОВАНИЯ КОНТРАКТА

## Обязательные файлы (CORE)

1. **work_orders/models.py** (1139 строк)
   - Почему: Полная схема данных WorkOrder + 14 связанных моделей
   - Что дать: Секции WorkOrder (lines 550-748) + связанные модели

2. **work_orders/admin.py** (199 строк)
   - Почему: ТОЧНОЕ определение 6 fieldsets (вкладок)
   - Что дать: WorkOrderAdmin (lines 106-151)

3. **work_orders/views.py** (451 строка)
   - Почему: API actions, permission guards, validation
   - Что дать: WorkOrderDetailView (lines 134-153), API endpoints (lines 289-450)

## Важные файлы (IMPORTANT)

4. **work_orders/templates/work_orders/work_order_detail.html** (313 строк)
   - Почему: Custom UI реализация, visible_when правила inline
   - Что дать: Полный файл

5. **work_orders/templates/work_orders/work_order_create.html** (125 строк)
   - Почему: Форма создания, 5 полей
   - Что дать: Полный файл

6. **work_orders/urls.py** (37 строк)
   - Почему: Маршрутизация, URL patterns
   - Что дать: Полный файл

## Полезные файлы (USEFUL)

7. **work_orders/templates/work_orders/base.html** (133 строки)
   - Почему: Bootstrap layout, navigation, global CSS
   - Что дать: CSS section (lines 16-66)

8. **portal/models.py** (фрагменты)
   - Почему: FK связи (ServicesCatalog, ServiceObject)
   - Что дать: Определения ServicesCatalog, ServiceObject

9. **nsi/models.py** (фрагменты)
   - Почему: FK связи (Company)
   - Что дать: Определение Company

## Опциональные файлы (OPTIONAL)

10. **work_orders/migrations/0002_initial_tables.py**
    - Почему: Initial schema, может содержать полезные комментарии
    - Что дать: WorkOrder CREATE TABLE statement

11. **MD_DB/request_management_architecture.md** (если существует)
    - Почему: Архитектурные решения, контекст
    - Что дать: Полный файл

---

# РЕКОМЕНДАЦИИ ПО ДАЛЬНЕЙШИМ ДЕЙСТВИЯМ

## БЛИЖАЙШИЕ ШАГИ (1-2 недели)

1. **ВЫБРАТЬ SINGLE SOURCE OF TRUTH**: Определить, Django Admin или Custom UI является каноничным набором полей

2. **РЕАЛИЗОВАТЬ ИЛИ УДАЛИТЬ** pause/resume actions: Убрать кнопки из template или добавить backend

3. **СОЗДАТЬ FORMS.PY**: Вынести validation логику из views.py в отдельный файл

4. **ДОБАВИТЬ REST API**: Implement serializers + viewsets для WorkOrder

5. **ДЕКУПЛИРОВАТЬ TEMPLATE LOGIC**: Вынести visible_when правила из template в metadata или Python

## СРЕДНЕСРОЧНЫЕ ШАГИ (1-2 месяца)

6. **ВВЕСТИ PRESENTER LAYER**: Вынести логику подготовки данных из views

7. **EXTRACT JAVASCRIPT**: Вынести AJAX calls из template в отдельные .js modules

8. **STANDARDIZE ACTIONS**: Единый подход к modal vs inline actions

9. **IMPLEMENT SLA UI**: Добавить отображение SLA timers

10. **IMPLEMENT ATTACHMENT UI**: Добавить загрузку фото в custom UI

## ДОЛГОСРОЧНЫЕ ШАГИ (3-6 месяцев)

11. **METADATA-DRIVEN UI FRAMEWORK**: Разработать или выбрать framework для metadata-driven forms

12. **MIGRATION PLAN**: План миграции с текущей dual implementation на metadata-driven

13. **COMPONENT LIBRARY**: Создать reusable UI components (Badge, Timeline, Modal)

14. **RULE ENGINE**: Ввести expressive rule engine для visible_when, required_when, permission_guard

15. **FIGMA INTEGRATION**: Настроить двунаправленную синхронизацию metadata ↔ Figma

---

**КОНЕЦ ОТЧЕТА**

---

Generated by: Claude (Senior Django Analyst + UI Contract Extractor)
Date: 2026-03-28
Total files analyzed: 7
Total lines of code analyzed: ~2500
Reliability: EXACT (90%), INFERRED (10)
