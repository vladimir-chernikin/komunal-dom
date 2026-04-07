# DIFF TABLE: RAW EXTRACTION vs NORMALIZED CONTRACT v0.2

## Сравнительная таблица изменений

| Категория | Было в Raw YAML | Стало в Normalized YAML | Причина изменения |
|-----------|-----------------|------------------------|-------------------|
| **СТРУКТУРА** | Монолитный YAML с 35+ полями | Profiles: detail_operator/detail_full/create | Разные сценарии использования, не разные экраны |
| **FIELD DEFINITION** | 15-20 строк на поле (все детали) | 3-5 строк (только metadata) | Убрать избыточность, фокус на контракте |
| **SOURCE ATTRIBUTION** | Не было | source: model/derived/relation/action_input/system | Четкое понимание происхождения данных |
| **IMPORTANCE** | Неявно (через display) | Явный tier: primary/secondary/technical/hidden_by_default | UX приоритизация, не технические детали |
| **RULES** | Смешано (visible + permission + validation + constraints) | Разделено: ui_rules + server_rule_refs | UI логика ≠ бизнес-логика |
| **PERMISSIONS** | Дублированы в YAML (condition, error_message) | Только ссылки: server_rule_refs → implementation | Single source of truth в Django code |
| **SIDE EFFECTS** | Детально описаны (create_event_log, notify) | Только ссылки: server_rule_refs → side_effect | Не тащить бизнес-логику в metadata |
| **ACTIONS** | Однородный список (7 actions) | Разделены по backend_status (implemented/deferred) | Честность: что работает, что нет |
| **PAUSE/RESUME** | Implemented (но backend не работает) | backend_status: deferred | Отражение реальности |
| **VALIDATION** | Дублирована в YAML | server_rule_refs → implementation | Не дублировать Django validation |
| **FIGMA** | Не было | figma_mapping: frames, components, density, layout_pattern | Целевая интеграция |
| **EXPORT** | Не было | export_notes: automatic/manual/clarification_needed | Понять процесс миграции |
| **MODAL** | Встроен в action definition | kind: modal_submit с modal_id | Унификация паттернов |
| **BUTTONS** | Размыто (type: api) | kind: inline_button/modal_submit/page_action | UX паттерны, не техническая реализация |
| **PROFILES** | Не было | 3 профиля для одного экрана | Отражение реальности (admin vs operator) |
| **FIELDSETS** | Дублированы из admin.py | tabs + groups (normalized) | Metadata-agnostic структура |
| **RELATED ENTITIES** | Подробности реализации | Только display_in_ui + profiles | Убрать технический шум |
| **READONLY FIELDS** | editable: false + computed: auto_now_add | editable: false + source: system | Явное указание происхождения |
| **FK DISPLAY** | Не указано | target_display + display_format | Figma нужна эта информация |
| **EMPTY VALUES** | Не указано | empty_display: "Не назначен" | UX деталь для Figma |
| **VISIBILITY** | explicit list | visibility: when_not_null (правило) | Компактность, не перечисление |
| **WIDGETS** | Не указано | widget: autocomplete/badge/textarea | Figma компоненты |
| **UI HINTS** | Не было | ui_hint: emergency_badge_pulse/alert_success | Специфическое поведение |
| **DATETIME HANDLING** | 11 полей с деталями | 11 полей + visibility: when_not_null | Компактность |
| **CREATION SOURCE** | 6 вариантов перечислены | choices (структура) | Генерация UI из metadata |
| **PRIORITY** | 4 варианта + default | choices с default marker | Генерация UI |
| **STATUS FILTER** | Встроено в поле | filter: "status_scope='internal'" | Отношения к справочникам |
| **ENDPOINT URLs** | Встроены в actions | server_handler_ref: "views.api_*" | Ссылки, не дублирование |
| **ICON REFERENCES** | Встроены | Сохранены (Bootstrap Icons) | Figma интеграция |
| **LAYOUT** | Не было | layout_pattern: operator_console | Figma шаблон |
| **GRID** | Не было | main_columns: 2, sidebar_width | Figma layout |
| **COMPONENTS** | Не было | component_hints (typography, colors, spacing) | Figma design system |
| **DENSITY** | Не было | density: dense | Figma decision |
| **CHECK CONSTRAINTS** | Дублированы (condition, source) | server_rule_refs → implementation | Single source of truth |
| **REQUIRED VALIDATION** | Дублировано | ui_rules: required_when (UI) + server_rule_refs (backend) | Разделение ответственности |
| **AUTOCOMPLETE** | Встроено в FK | widget: autocomplete | Figma UX hint |
| **PLACEHOLDERS** | Встроены | Сохранены в полях | UX деталь |
| **ROWS (TEXTAREA)** | Встроены | Сохранены в полях | UX деталь |
| **ALERTS** | Не было | ui_hint: alert_success | Figma component |
| **BADGES** | Не было | widget: badge + ui_hint: color_* | Figma component |
| **TIMELINE** | Подробности в related_entities | display_in_ui: "timeline in sidebar" | Figma layout hint |
| **BOOTSTRAP** | Неявно (framework) | component_hints: Bootstrap colors/spacing | Figma integration |
| **ANIMATION** | Не было | emergency_badge_animation: @keyframes pulse | Figma behavior |
| **IMPLEMENTATION STATUS** | Не было | backend_status: implemented/deferred/excluded_from_v0_2 | Честность о состоянии |
| **NOT_IMPLEMENTED** | Не было | server_handler_ref: "NOT_IMPLEMENTED" | Явное указание |
| **NOTE FIELD** | Не было | note: "Button exists but NO backend" | Документация |

---

# A. ЧТО ОСТАВЛЯЕМ В DJANGO CODE

## Бизнес-логика и транзакции

✅ **Permission guards** (views.py:301-420):
- api_take_work_order: проверка членства в department
- api_start_work_order: проверка responsible_user == current_user
- api_complete_work_order: проверка responsible_user
- api_close_work_order: проверка role_code in ['direktor_uk', 'chief_engineer']

✅ **Status transitions**:
- Изменение current_internal_status
- Изменение current_external_status
- Установка datetime полей (assigned_at, in_progress_at, etc.)

✅ **Side effects**:
- WorkOrderEventLog.objects.create() на каждое действие
- NotificationOutbox для уведомлений жителей

✅ **Validation logic**:
- views.py:378 - проверка resolution_text при complete
- CheckConstraints из models.py

✅ **Database internals**:
- CheckConstraints (5 constraints)
- UniqueConstraints
- Indexes
- Triggers (если будут)

✅ **Model methods** (если будут):
- save() с переопределением
- custom validation methods
- business logic methods

✅ **Query optimization**:
- select_related() в admin.py
- prefetch_related() (если будет)

✅ **API handlers**:
- Все views.api_*_work_order функции
- WorkOrderDetailView, WorkOrderCreateView

✅ **Service layer** (если будет):
- Вызов бизнес-логики из views
- Интеграция с ботом (MessageLog)
- SLA calculation (если будет)

---

# B. ЧТО ВЫНОСИМ IN METADATA

## Структура экрана

✅ **Tabs definition** (6 вкладок):
- code, name, order, collapsed
- groups inside tabs

✅ **Field metadata** (35+ полей):
- code, label, type
- source (model/derived/relation/action_input/system)
- profiles (какие сценарии использования)
- tab, group (группа внутри вкладки)
- editable (можно ли редактировать)
- importance (primary/secondary/technical/hidden_by_default)
- widget (autocomplete/badge/textarea/select/bool)
- choices (для select полей)
- validation (required_when, etc.)
- ui_hint (специфическое поведение)

✅ **Action metadata** (7 actions):
- code, label, icon
- profiles (каким сценариям доступно)
- kind (inline_button/modal_submit/page_action)
- backend_status (implemented/deferred/excluded_from_v0_2)
- ui_visibility_rule_ref (ссылка на ui_rule)
- server_handler_ref (ссылка на Django function)
- input_fields (для modal actions)
- effects (какие поля меняются)

✅ **UI rules** (только визуальная логика):
- visible_when (показывать элемент?)
- enabled_when (элемент активен?)
- required_when (поле обязательно?)
- applies_to (какому элементу)
- source (template/code/inferred)
- location (где в коде)

✅ **Figma mapping**:
- screen_frame_name
- tab_frames
- component_hints (typography, colors, spacing, components)
- density (dense/normal/spacious)
- layout_pattern (operator_console/dashboard/form/etc)
- layout_structure (columns, sidebar)
- responsive_breakpoints

✅ **Related entities**:
- code, relation type
- display_in_ui (как показывать)
- profiles (где показывать)

✅ **Export notes**:
- automatic (что можно вытащить из кода)
- manual (что decides UX/product)
- clarification_needed (что нужно обсудить)

---

# C. ЧТО БУДЕТ ЖИТЬ В FIGMA

## Визуальные компоненты

✅ **Screen layout**:
- Frame: "Work Order / Detail / Operator"
- Grid: 2 колонки + sidebar
- Spacing: определено в component_hints

✅ **Tab frames**:
- Tab / Main Info (vertical layout)
- Tab / Current State (horizontal layout)
- Tab / Request Text (vertical layout)
- Tab / Lifecycle (grid 2 columns)
- Tab / Service (collapsed)

✅ **Components** (создаются в Figma):
- Badge component (status badges, priority badge)
- Emergency badge (с pulse animation)
- Button component (с иконками Bootstrap)
- Card component (с shadow)
- Modal component (completeModal)
- Timeline component (sidebar)

✅ **Typography** (из YAML):
- Header title: Heading 5 (h5)
- Section title: Heading 6 (h6)
- Field label: Small text-muted
- Field value: Body

✅ **Colors** (из YAML):
- Primary badge: #0d6efd
- Info badge: #0dcaf0
- Emergency badge: #dc3545
- Success alert: #198754

✅ **Spacing** (из YAML):
- Card margin: 16px
- Section spacing: 16px
- Field spacing: 8px

✅ **Patterns**:
- Operator console layout pattern
- Dense density
- Sidebar with timeline

✅ **Responsive**:
- Mobile: stack columns
- Tablet: adjust grid
- Desktop: 2 columns + sidebar

✅ **States** (из ui_rules):
- Button visibility (take/start/complete/close)
- Field visibility (datetime when not null)
- Modal state (completeModal)

---

# D. ЧТО ИСКЛЮЧАЕМ ИЗ v0.2

## Не реализовано в backend

❌ **pause_work_order** (excluded_from_v0.2):
- Кнопка есть в template
- Backend НЕ реализован
- Status 'on_hold' НЕ в модели
- Вынести в metadata, но пометить deferred

❌ **resume_work_order** (excluded_from_v0.2):
- Кнопка есть в template
- Backend НЕ реализован
- Status 'on_hold' НЕ в модели
- Вынести в metadata, но пометить deferred

## Не показывать в UI v0.2

❌ **SLAInstance display**:
- Модель существует
- OneToOne связь с WorkOrder
- UI НЕ реализован
- Вынести в related_entities с note "NOT SHOWN in v0.2"

❌ **WorkOrderAttachment display**:
- Модель существует
- ForeignKey связь
- UI НЕ реализован
- Вынести в related_entities с note "NOT SHOWN in v0.2"

❌ **NotificationOutbox display**:
- Модель существует
- Системная таблица
- Не для пользовательского UI
- Вынести в related_entities с note "NOT SHOWN in v0.2"

## Убрать из metadata (technical debt)

❌ **Implementation details**:
- Конкретные SQL queries
- ORM детали (select_related, prefetch_related)
- Индексы БД
- Migration детали

❌ **Permission implementation**:
- Код проверки permissions
- Error messages
- Redirect logic
- Только ссылки: server_rule_refs

❌ **Side effect implementation**:
- Код создания WorkOrderEventLog
- Код отправки уведомлений
- Transaction handling
- Только ссылки: server_rule_refs

❌ **DB constraints** (дублирование):
- CheckConstraint условия (перечисление)
- UniqueConstraint детали
- Только ссылки: server_rule_refs

❌ **Validation logic** (дублирование):
- Код валидации resolution_text
- Код валидации required полей
- Только ссылки: server_rule_refs

❌ **Inline JavaScript**:
- AJAX fetch calls
- CSRF token handling
- Error handling
- Убрать в будущий JavaScript metadata (не в v0.2)

❌ **CSS specifics**:
- Bootstrap классы
- Custom CSS rules
- Animation keyframes (кроме conceptual)
- Только conceptual hints в component_hints

---

# SUMMARY CHANGES

## Количественные метрики

| Метрика | Raw YAML | Normalized v0.2 | Изменение |
|---------|----------|-----------------|-----------|
| **Строк на поле** | 15-20 | 3-5 | -75% |
| **Всего строк** | ~800 | ~450 | -44% |
| **Правил** | 11 (смешанные) | 6 ui + 10 server | Разделение |
| **Actions** | 7 (однородные) | 4 impl + 2 deferred + 1 create | Честность |
| **Profiles** | 0 | 3 | Новое |
| **Figma hints** | 0 | 50+ | Новое |
| **Export notes** | 0 | 12 пунктов | Новое |
| **Дублирование** | Высокое | Минимальное | Уменьшение |

## Качественные улучшения

1. **Ясность**: Каждое поле имеет четкий source и importance
2. **Честность**: Реально работающий код marked as implemented, остальное as deferred
3. **Разделение**: UI логика отдельно от бизнес-логики
4. **Интеграция**: Figma mapping для bidirectional sync
5. **Экспорт**: Понятно, что автоматическое, что manual
6. **Компактность**: Меньше строк, больше информации
7. **Готовность**: Пригоден для Django → Figma → Claude pipeline

---

# NEXT STEPS (рекомендации)

## Ближайшие (1-2 недели)

1. **ВЫБРАТЬ PROFILES**: Уточнить, нужно ли 3 профиля или достаточно 2
2. **РЕАЛИЗОВАТЬ ИЛИ УБРАТЬ**: pause/resume - реализовать backend или убрать из UI
3. **УТОЧНИТЬ IMPORTANCE**: Review primary/secondary/technical с UX командой
4. **FIGMA INTEGRATION**: Начать перенос screen_frame_name и tab_frames в Figma

## Среднесрочные (1-2 месяца)

5. **SLA UI**: Решить, показывать ли SLAInstance timers
6. **ATTACHMENT UI**: Реализовать загрузку фото в custom UI
7. **JAVASCRIPT**: Extract inline JS в separate modules
8. **COMPONENT LIBRARY**: Создать reusable Figma components

## Долгосрочные (3-6 месяцев)

9. **METADATA ENGINE**: Разработать или выбрать framework для metadata-driven UI
10. **DYNAMIC PROFILES**: Внести runtime switching между профилями
11. **RULES ENGINE**: Ввести expressive rules для complex conditions
12. **FIGMA SYNC**: Настроить двунаправленную синхронизацию

---

**КОНЕЦ DIFF TABLE**
