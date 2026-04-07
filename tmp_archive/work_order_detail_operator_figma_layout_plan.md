FIGMA_CONTEXT_STATUS: MISSING

# WorkOrder Detail Operator — Figma Layout Plan v1.0

**Screen:** Work Order Detail (Profile: detail_operator)
**Style:** Плотная операционная форма (1С / диспетчерская)
**Stack:** Bootstrap 5 + Server-rendered Django
**Sources:** Form contract + Current Django template (Figma context: MISSING)

---

## SUMMARY

**Target:** Перестроить экран WorkOrder из "карточки с кнопками" в "плотную операционную форму".

**Key changes from current UI:**
1. Компактная шапка (нет work_order_no в detail_operator)
2. Action bar под шапкой (все действия на виду)
3. 3 колонки вместо 2 (контент | история | метрики)
4. Статусы в badge-bar (горизонтально, не вертикально)
5. Lifecycle/dates в отдельном блоке внизу
6. Technical/secondary поля скрыты или в правой колонке

**Sources used:**
- ✅ Form contract: tmp_archive/work_order_contract_v0.2_normalized.yaml
- ✅ Current template: work_orders/templates/work_orders/work_order_detail.html
- ✅ Current view: work_orders/views.py (WorkOrderDetailView context)
- ❌ Figma design: MISSING

---

## SCREEN STRUCTURE (Top → Bottom)

### 1. HEADER BAR (Fixed, 56px height)

```
┌─────────────────────────────────────────────────────────────┐
│ [breadcrumb] Заявка ЖКХ › Текущая                          │
└─────────────────────────────────────────────────────────────┘
```

**Components:**
- Breadcrumb: "Дашборд › Текущая"
- Right side: emergency badge (if is_emergency)

**Fields:**
- is_emergency → badge "АВАРИЯ" (red, pulse animation if true)

---

### 2. ACTION BAR (Fixed, 64px height)

```
┌─────────────────────────────────────────────────────────────┐
│ [BUTTON TAKE] [BUTTON START] [BUTTON COMPLETE] [STATUS]    │
└─────────────────────────────────────────────────────────────┘
```

**Layout:** Horizontal flex, left-aligned buttons, right-aligned status

**Components:**
- take_work_order (button: green, icon bi-hand-index-thumb)
- start_work_order (button: success, icon bi-play-circle)
- complete_work_order (button: primary, icon bi-check-circle)
- current_internal_status (badge: primary, large)

**Visibility rules:**
- take_work_order: visible when responsible_user is NULL
- start_work_order: visible when status='accepted_by_executor' AND responsible_user=current_user
- complete_work_order: visible when status='in_progress' AND responsible_user=current_user

**NOT shown (backend_status=deferred):**
- pause_work_order (excluded from v1)
- resume_work_order (excluded from v1)

---

### 3. BADGE BAR (Status & Priority)

```
┌─────────────────────────────────────────────────────────────┐
│ [INTERNAL: accepted_by_executor] [EXTERNAL: в работе]      │
│ [PRIORITY: Высокий]                                         │
└─────────────────────────────────────────────────────────────┘
```

**Layout:** 2 rows, horizontal flex

**Row 1 — Statuses:**
- current_internal_status → badge primary (large)
- current_external_status → badge info (large)

**Row 2 — Priority:**
- priority_code → badge (color by priority)
- is_emergency → badge danger (if true, duplicate from header)

**Fields:**
- current_internal_status (primary)
- current_external_status (primary)
- priority_code (primary)
- is_emergency (primary)

---

### 4. MAIN CONTENT AREA (3 columns, 12 grid)

```
┌─────────────────────────────────────────────────────────────────┐
│ LEFT (6 cols)              │ MIDDLE (4 cols)   │ RIGHT (2 cols) │
│                            │                   │                │
│ [Текст заявки]             │ [История]         │ [Метрики]      │
│ [Описание]                 │ [Timeline]        │ [Даты]         │
│ [Решение]                  │                   │ [Исполнитель]  │
│ [Lifecycle/dates]          │                   │ [Подразделение]│
└─────────────────────────────────────────────────────────────────┘
```

**Grid:** Bootstrap col-lg-6 | col-lg-4 | col-lg-2

---

### 5. LEFT COLUMN (Primary Content)

**Order top → bottom:**

#### 5.1 Request Text Block
```
┌─────────────────────────────────────────────────────────────┐
│ Описание заявки                                             │
┌─────────────────────────────────────────────────────────────┐
│ Текст заявки...                                            │
│                                                            │
│ [Дополнительные сведения] (если есть)                      │
└─────────────────────────────────────────────────────────────┘
```

**Fields:**
- original_request_text (primary) — large text, multiline
- additional_info_text (secondary) — hidden in detail_operator

#### 5.2 Resolution Block (conditional)
```
┌─────────────────────────────────────────────────────────────┐
│ Решение                                                     │
┌─────────────────────────────────────────────────────────────┐
│ Текст решения...                                            │
└─────────────────────────────────────────────────────────────┘
```

**Fields:**
- resolution_text (primary) — visible when NOT null, alert-success styling

**Hidden in v1:**
- resolution_text input (only via complete_work_order modal)

#### 5.3 Lifecycle Dates Block
```
┌─────────────────────────────────────────────────────────────┐
│ Жизненный цикл                                             │
├─────────────────────────────────────────────────────────────┤
│ Создана: 28.03.2026 14:30                                 │
│ Назначена: 28.03.2026 14:35                               │
│ В работе с: 28.03.2026 15:00                              │
│ Выполнена: —                                              │
└─────────────────────────────────────────────────────────────┘
```

**Fields:**
- created_at (primary)
- assigned_at (primary, visible when NOT null)
- in_progress_at (primary, visible when NOT null)
- completed_at (primary, visible when NOT null)

**Hidden in detail_operator:**
- accepted_at, resident_contacted_at, localized_at, closed_at, cancelled_at, reopened_at

---

### 6. MIDDLE COLUMN (Timeline)

```
┌─────────────────────────────────────────────────────────────┐
│ История событий                                             │
├─────────────────────────────────────────────────────────────┤
│ 28.03.2026 15:00                                           │
│ Иванов И.И.: Начато выполнение                             │
│ [badge: В работе]                                          │
├─────────────────────────────────────────────────────────────┤
│ 28.03.2026 14:35                                           │
│ System: Назначена на Петрова П.П.                          │
│ [badge: Принята исполнителем]                              │
├─────────────────────────────────────────────────────────────┤
│ 28.03.2026 14:30                                           │
│ System: Заявка зарегистрирована                            │
│ [badge: Новая]                                             │
└─────────────────────────────────────────────────────────────┘
```

**Related entity:** WorkOrderEventLog (FK work_order → events)

**Display format:**
- event_datetime (timestamp)
- author_user (if exists) → "Ф.И.О.:"
- text_value → event description
- new_status → badge (if exists)

**Current implementation:** work_order_detail.html:179-194 (timeline in right column)

---

### 7. RIGHT COLUMN (Metrics)

**Order top → bottom:**

#### 7.1 Service & Object
```
┌─────────────────────────────────────────────────────────────┐
│ Услуга                                                     │
│ Сантехнические работы                                       │
├─────────────────────────────────────────────────────────────┤
│ Подразделение                                               │
│ Сантехническая служба                                      │
├─────────────────────────────────────────────────────────────┤
│ Исполнитель                                                 │
│ Петров П.П.                                                │
└─────────────────────────────────────────────────────────────┘
```

**Fields:**
- service.scenario_name (primary)
- department.department_name (primary)
- responsible_user.get_full_name (primary, "Не назначен" if null)

**Hidden in detail_operator:**
- object.service_object_id (technical, not shown in v1)
- company.name (detail_full only)

#### 7.2 Technical Metrics (collapsible)
```
┌─────────────────────────────────────────────────────────────┐
│ Техническая информация [▼]                                 │
├─────────────────────────────────────────────────────────────┤
│ ID: #12345                                                 │
│ Source: Бот (JSON)                                         │
│ Test: Нет                                                  │
└─────────────────────────────────────────────────────────────┘
```

**Fields:**
- work_order_no (technical, shown in collapsed block)
- creation_source (technical, shown in collapsed block)
- is_test (technical, shown in collapsed block)

**Collapsed by default:** click to expand

---

## FIELD CLASSIFICATION (detail_operator)

### PRIMARY (всегда показывать, 17 полей)
- service.scenario_name
- department.department_name
- responsible_user.get_full_name
- current_internal_status.short_name_ru
- current_external_status.short_name_ru
- priority_code
- is_emergency
- original_request_text
- resolution_text (if NOT null)
- created_at
- assigned_at (if NOT null)
- in_progress_at (if NOT null)
- completed_at (if NOT null)
- WorkOrderEventLog (timeline)

### SECONDARY (показывать в expanded view, 0 полей)
- detail_operator profile НЕ использует secondary поля

### TECHNICAL (скрыть или collapsible, 3+ полей)
- work_order_no (in technical block)
- creation_source (in technical block)
- is_test (in technical block)

### HIDDEN_IN_DETAIL_OPERATOR (не показывать, 20+ полей)
- company.name
- object.service_object_id
- route
- additional_info_text
- resident_user
- parent_work_order
- request_intake
- accepted_at, resident_contacted_at, localized_at, closed_at, cancelled_at, reopened_at
- message_log_ref
- completed_by_user, closed_by_user, cancelled_by_user
- updated_at

---

## ACTIONS (detail_operator, backend_status filter)

### IMPLEMENTED (показывать, 4 действия)
- take_work_order → button "Взять заявку в работу" (green, icon bi-hand-index-thumb)
- start_work_order → button "Начать выполнение" (success, icon bi-play-circle)
- complete_work_order → button "Завершить выполнение" (primary, icon bi-check-circle, modal)
- create_work_order → page action "Создать заявку" (not in detail screen)

### DEFERRED (НЕ показывать в v1, 2 действия)
- pause_work_order → hidden (backend NOT implemented)
- resume_work_order → hidden (backend NOT implemented, status 'on_hold' NOT in model)

### EXCLUDED_FROM_V0_2 (не показывать, 1 действие)
- close_work_order → hidden (detail_full only)

---

## FIGMA FRAMES/COMPONENTS TO CREATE

### Page Frames
1. **Work Order / Detail / Operator** (desktop, ≥992px)
2. **Work Order / Detail / Operator / Tablet** (768px - 992px, collapse right column)
3. **Work Order / Detail / Operator / Mobile** (<768px, stack everything)

### Component Library
1. **Header / Bar** (56px height, fixed)
   - Header / Breadcrumb
   - Header / Emergency Badge

2. **Action / Bar** (64px height, fixed)
   - Action / Button / Take (green, icon bi-hand-index-thumb)
   - Action / Button / Start (success, icon bi-play-circle)
   - Action / Button / Complete (primary, icon bi-check-circle)
   - Action / Badge / Status (large)

3. **Badge / Bar** (auto height)
   - Badge / Status / Internal (primary)
   - Badge / Status / External (info)
   - Badge / Priority (color by priority)
   - Badge / Emergency (danger, pulse animation)

4. **Content / Block / Request Text** (auto height)
   - Content / Label / "Описание заявки"
   - Content / Text / Original (large)
   - Content / Text / Additional (small, muted)

5. **Content / Block / Resolution** (auto height, conditional)
   - Content / Label / "Решение"
   - Content / Alert / Success
   - Content / Text / Resolution

6. **Content / Block / Lifecycle** (auto height)
   - Content / Label / "Жизненный цикл"
   - Content / Grid / 2 columns
   - Content / Field / Date (4 rows: created, assigned, in_progress, completed)

7. **Sidebar / Timeline** (fixed height, scrollable)
   - Timeline / Item (repeating)
   - Timeline / Timestamp
   - Timeline / Author (optional)
   - Timeline / Text
   - Timeline / Badge (optional)

8. **Sidebar / Metrics** (auto height)
   - Metrics / Row / Service
   - Metrics / Row / Department
   - Metrics / Row / Responsible
   - Metrics / Block / Technical (collapsible)

9. **Modal / Complete** (centered, 600px width)
   - Modal / Title / "Завершить выполнение заявки"
   - Modal / Field / Resolution Text (textarea, 5 rows, required)
   - Modal / Footer / Cancel + Complete buttons

### Design Tokens
1. **Typography**
   - Header / Title → Heading 5 (h5)
   - Header / Label → Heading 6 (h6)
   - Field / Label → Small text-muted
   - Field / Value → Body
   - Timeline / Timestamp → Small text-muted

2. **Colors**
   - Primary badge → Bootstrap Primary (#0d6efd)
   - Info badge → Bootstrap Info (#0dcaf0)
   - Success alert → Bootstrap Success (#198754)
   - Emergency badge → Bootstrap Danger (#dc3545) + pulse animation

3. **Spacing**
   - Card margin-bottom → 1rem (16px)
   - Section spacing → 1rem (16px)
   - Field spacing → 0.5rem (8px)
   - Timeline item spacing → 1rem (16px)

4. **Special**
   - Emergency badge animation → @keyframes pulse (2s infinite)
   - Timeline scrollbar → slim, auto-hide

---

## WHAT TO TAKE FROM CONTRACT DIRECTLY

1. **Field list for detail_operator** (lines 115-162, 166-227, 231-269, 335-377)
2. **Action definitions** (lines 607-663)
3. **UI visibility rules** (lines 743-802)
4. **Figma component hints** (lines 931-958)
5. **Layout structure** (lines 960-969)
6. **Responsive breakpoints** (lines 966-969)

---

## WHAT TO TAKE FROM CURRENT DJANGO UI

1. **Bootstrap 5 card pattern** (work_order_detail.html:20-128)
2. **Timeline implementation** (work_order_detail.html:179-194)
3. **Action bar pattern** (work_order_detail.html:132-158)
4. **Modal pattern** (work_order_detail.html:201-225)
5. **Emergency badge animation** (implied from is_emergency field)
6. **3-column responsive grid** (col-lg-8 | col-lg-4 → col-lg-6 | col-lg-4 | col-lg-2)

---

## WHAT NOT TO SHOW IN V1

1. **Secondary fields** (0 для detail_operator, но если будут — скрывать)
2. **Technical fields** (work_order_no, creation_source, is_test → collapsible)
3. **Hidden_by_default fields** (updated_at)
4. **Deferred actions** (pause_work_order, resume_work_order)
5. **Detail_full exclusive fields** (company, object, parent_work_order, resident_user, etc.)
6. **Extended lifecycle dates** (accepted_at, resident_contacted_at, localized_at, closed_at, cancelled_at, reopened_at)
7. **Service tab fields** (message_log_ref, completed_by_user, closed_by_user, cancelled_by_user)
8. **Relations tab fields** (request_intake, resident_user, parent_work_order)

---

## HOW TO QUICKLY BUILD THIS SCREEN IN FIGMA (10-15 steps)

### Step 1: Create page frames
- Create 3 frames: Desktop (1440px), Tablet (768px), Mobile (375px)
- Name them: "Work Order / Detail / Operator [Device]"

### Step 2: Build component library
- Create 9 component sets (see FIGMA FRAMES/COMPONENTS above)
- Use Bootstrap color tokens (#0d6efd, #0dcaf0, #198754, #dc3545)
- Use Bootstrap spacing tokens (4px, 8px, 16px)

### Step 3: Layout desktop frame (1440px width)
- Add header bar (56px height, fixed top)
- Add action bar (64px height, fixed below header)
- Add badge bar (auto height, below action bar)
- Add 3-column grid (col-lg-6 | col-lg-4 | col-lg-2)
- Set page padding: 16px

### Step 4: Build left column (primary content)
- Add "Request Text Block" component
- Add "Resolution Block" component (conditional, hidden by default)
- Add "Lifecycle Dates Block" component
- Set vertical spacing: 16px between blocks

### Step 5: Build middle column (timeline)
- Add "Sidebar / Timeline" component
- Add 3-5 sample timeline items
- Set timeline item spacing: 16px
- Make scrollable if content > 600px height

### Step 6: Build right column (metrics)
- Add "Sidebar / Metrics" component
- Add 3 metric rows: Service, Department, Responsible
- Add "Technical Block" component (collapsed by default)
- Set vertical spacing: 16px between rows

### Step 7: Add action buttons
- Add "Take" button (green, icon bi-hand-index-thumb)
- Add "Start" button (success, icon bi-play-circle)
- Add "Complete" button (primary, icon bi-check-circle)
- Add status badge (large, right-aligned)
- Set button spacing: 8px

### Step 8: Add status badges
- Add internal status badge (primary)
- Add external status badge (info)
- Add priority badge (color by priority)
- Add emergency badge (danger, pulse animation)
- Set badge spacing: 8px

### Step 9: Build modal
- Create modal frame (600px width, centered)
- Add title: "Завершить выполнение заявки"
- Add textarea: "Текст решения" (5 rows, required)
- Add footer: Cancel + Complete buttons

### Step 10: Responsive adaptation (tablet + mobile)
- Tablet: collapse right column into middle column
- Mobile: stack everything vertically
- Hide non-essential elements on mobile
- Test at 3 breakpoints: 375px, 768px, 1440px

### Step 11: Add interactions (optional)
- Add hover states for buttons
- Add focus states for inputs
- Add active states for badges
- Add pulse animation for emergency badge

### Step 12: Export assets
- Export icons as SVG (bi-hand-index-thumb, bi-play-circle, bi-check-circle)
- Export component documentation
- Export responsive layout guide

### Step 13: Review against contract
- Check: all 17 primary fields included
- Check: 4 implemented actions included
- Check: 2 deferred actions excluded
- Check: 3 columns layout matches plan
- Check: density = "dense"

### Step 14: Test with sample data
- Use sample WorkOrder from contract
- Test all action visibility rules
- Test conditional blocks (resolution, lifecycle dates)
- Test timeline with 5-10 events

### Step 15: Handoff to development
- Provide Figma file URL
- Provide component library documentation
- Provide responsive layout guide
- Provide interaction states

**Estimated time:** 2-3 hours for experienced Figma user

---

## NEXT_FOR_CHATGPT

**Prompt for next step (Django implementation):**

```
Реализуй экран WorkOrder Detail Operator по Figma layout plan:

1. Создай новый template: work_orders/templates/work_orders/work_order_detail_operator.html
2. Обнови view: work_orders/views.py::WorkOrderDetailView (добавить context для timeline)
3. Используй Bootstrap 5 + 3-column grid (col-lg-6 | col-lg-4 | col-lg-2)
4. Следуй структуре из plan: Header → Action Bar → Badge Bar → 3-Column Content
5. Скрой deferred actions (pause/resume)
6. Скрой technical поля (work_order_no, creation_source, is_test) в collapsible block
7. Сохрани существующий timeline pattern
8. Добавь modal для complete_work_order (resolution_text input)
9. Тестируй на 3 breakpoints: mobile, tablet, desktop

Sources:
- tmp_archive/work_order_contract_v0.2_normalized.yaml (profile: detail_operator)
- tmp_archive/work_order_detail_operator_figma_layout_plan.md
- work_orders/templates/work_orders/work_order_detail.html (current implementation)
```

---

## RISKS (расхождений между contract / Figma / Django)

### Risk 1: Figma Context Missing
**Impact:** Layout plan создан без визуального дизайна
**Mitigation:** Plan основан на contract + current UI, Figma можно добавить позже
**Probability:** Высокая (Figma URL не предоставлен)

### Risk 2: 3-Column Layout vs Current 2-Column
**Impact:** Существующая правая колонка (timeline) будет перемещена в среднюю колонку
**Mitigation:** Timeline pattern остается, меняется только позиция
**Probability:** Средняя

### Risk 3: Deferred Actions Hidden
**Impact:** Пользователи не увидят кнопки "Приостановить" и "Возобновить"
**Mitigation:** Backend не реализован, кнопки не работают, правильное решение для v1
**Probability:** Низкая

### Risk 4: Technical Fields Collapsible
**Impact:** Пользователи могут не найти work_order_no если он скрыт
**Mitigation:** work_order_num показан в header breadcrumb, technical block collapsible
**Probability:** Средняя

### Risk 5: Object Field Hidden in detail_operator
**Impact:** Оператор не увидит объект обслуживания
**Mitigation:** object в contract как primary для detail_operator, НО technical по сути
**Probability:** Средняя (уточнить у product)

### Risk 6: Density vs Readability
**Impact:** Плотная операционная форма может быть трудной для чтения
**Mitigation:** Использовать Bootstrap spacing tokens, тестировать с пользователями
**Probability:** Средняя

---

**END OF LAYOUT PLAN v1.0**
**Created:** 2026-03-29
**Author:** Claude (Figma + Django Layout Planner)
**Status:** READY FOR FIGMA IMPLEMENTATION
