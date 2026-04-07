# WorkOrder Detail Operator — Figma Build Steps для Новичка

**Что уже есть:**
- ✅ Пустой frame в Figma (node-id=1:2, белого цвета)
- ✅ Layout plan: tmp_archive/work_order_detail_operator_figma_layout_plan.md
- ✅ Figma URL: https://www.figma.com/design/C7LCmH1rUjeuqqjcwMDZvb/Komunalka---WorkOrder-UI?node-id=1-2

**Что мы собираем:**
- Экран "Заявка ЖКХ / Детально / Для оператора"
- Плотная операционная форма (стиль 1С / диспетчерская)
- 3 колонки: контент (6) | история (4) | метрики (2)
- Bootstrap 5 styling (отступы 4/8/16px, цвета #0d6efd, #0dcaf0, #198754, #dc3545)

---

## ШАГ 1: Открой frame и задай размеры

**Действия:**
1. Открой Figma file по URL выше
2. Найди frame "Work Order / Detail / Operator" (node-id=1:2)
3. Кликни по frame → откроется правая панель Design
4. В секции Frame задай размеры:
   - Width: `1440` (desktop)
   - Height: `900` (можно потом расширить)
5. Нажми Enter

**Проверь:** Frame теперь 1440×900px, белый фон

---

## ШАГ 2: Создай Auto Layout для всего экрана

**Действия:**
1. Убедись, что frame выбран (синяя обводка)
2. Нажми `Shift+A` → добавится Auto Layout
3. В правой панели Auto Layout задай:
   - **Direction:** Vertical (↓)
   - **Padding:** 16 (все стороны)
   - **Gap:** 16
   - **Alignment:** Top Left

**Проверь:** Frame теперь с Auto Layout, вертикальный, с отступами

---

## ШАГ 3: Создай HEADER BAR

**Что это:** Верхняя шапка с breadcrumb и emergency badge

**Действия:**
1. Выбери frame → нажми `+` (добавить слой)
2. Нажми `R` → создастся Rectangle
3. В правой панели задай:
   - Width: `1408` (1440 - 16×2 padding)
   - Height: `56`
   - Fill: `#FFFFFF` (белый)
   - Stroke: `none`
4. Нажми `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Horizontal (→)
   - **Padding:** 16 horizontal, 16 vertical
   - **Gap:** 8
   - **Alignment:** Center Left
   - **Distribution:** Pack

**Добавь текст breadcrumb:**
1. Выбери header bar → нажми `T` → текст
2. Введи текст: `Заявка ЖКХ › Текущая`
3. В правой панели Text:
   - Font: Inter (или системный)
   - Size: `14`
   - Weight: `400`
   - Color: `#6C757D` (серый)
4. Перетащи текст внутрь header bar

**Добавь placeholder для emergency badge:**
1. Нажми `R` → Rectangle
2. Размеры: 80×28
3. Fill: `#DC3545` (красный)
4. Скругли углы: Corner radius = `4`
5. Нажми `T` → текст "АВАРИЯ" внутри badge
6. Текст настройки: Size 12, Weight 600, Color #FFFFFF
7. Сгруппируй badge + текст (`Cmd+G` / `Ctrl+G`)
8. Перетащи вправо в header bar

**Переименуй:**
1. Выбери header bar → нажми `Cmd+R` / `F2`
2. Введи имя: `Header / Bar`

**Проверь:** Header bar 56px высотой, breadcrumb слева, emergency badge справа

---

## ШАГ 4: Создай ACTION BAR

**Что это:** Панель действий с кнопками и статусом

**Действия:**
1. Выбери frame → добавь новый Rectangle (`R`)
2. Размеры: 1408×64
3. Fill: `#F8F9FA` (серый, Bootstrap bg-light)
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Horizontal (→)
   - **Padding:** 16 horizontal, 16 vertical
   - **Gap:** 8
   - **Alignment:** Center Left
   - **Distribution:** Space between

**Создай кнопку "Взять заявку":**
1. Нажми `R` → Rectangle
2. Размеры: 200×40 (авто по тексту потом)
3. Fill: `#198754` (Bootstrap success, зеленый)
4. Corner radius: `4`
5. `Shift+A` → Auto Layout
6. Padding: 12×16, Gap: 8, Alignment: Center
7. Добавь текст (`T`): "Взять заявку в работу"
8. Текст: Size 14, Weight 500, Color #FFFFFF
9. Сгруппируй кнопку + текст (`Cmd+G`)
10. Переименуй в: `Action / Button / Take`

**Создай кнопку "Начать выполнение":**
1. Дублируй кнопку Take (`Cmd+D` / `Ctrl+D`)
2. Измени текст на: "Начать выполнение"
3. Fill: `#0D6EFD` (Bootstrap primary, синий)
4. Переименуй в: `Action / Button / Start`

**Создай кнопку "Завершить выполнение":**
1. Дублируй кнопку Start
2. Измени текст на: "Завершить выполнение"
3. Fill: `#0D6EFD` (оставь синим)
4. Переименуй в: `Action / Button / Complete`

**Создай status badge:**
1. Нажми `R` → Rectangle
2. Размеры: 160×32
3. Fill: `#0D6EFD` (primary)
4. Corner radius: `16` (сделай овальным)
5. Текст: "В работе" (или текущий статус)
6. Текст: Size 14, Weight 500, Color #FFFFFF
7. Сгруппируй badge + текст
8. Переименуй в: `Badge / Status / Current`

**Перетащи всё в Action Bar:**
1. Выбери 3 кнопки + 1 badge
2. Перетащи в Action Bar (кнопки слева, badge справа)
3. Убедись, что Auto Layout работает: кнопки слева с gap 8, badge справа

**Переименуй:** `Action / Bar`

**Проверь:** Action bar 64px высотой, 3 кнопки слева, status badge справа

---

## ШАГ 5: Создай BADGE BAR

**Что это:** Строка со статусами и приоритетом

**Действия:**
1. Выбери frame → добавь Rectangle (`R`)
2. Размеры: 1408×auto (авто по высоте)
3. Fill: `transparent` (прозрачный)
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Vertical (↓)
   - **Padding:** 0
   - **Gap:** 8
   - **Alignment:** Top Left

**Создай Row 1 — Statuses:**
1. Выбери Badge Bar → добавь Auto Layout (`Shift+A`)
2. Настройки:
   - **Direction:** Horizontal (→)
   - **Padding:** 0
   - **Gap:** 8
   - **Alignment:** Center Left
3. Добавь 2 badge (скопируй Badge / Status / Current):
   - Первый: "Принята исполнителем" (internal)
   - Второй: "В работе" (external)
4. Fill badges:
   - Internal: `#0D6EFD` (primary)
   - External: `#0DCAFE` (info)
5. Сгруппируй Row 1 → назови `Badge / Row / Statuses`

**Создай Row 2 — Priority:**
1. Дублируй Row 1
2. Оставь 1 badge: "Высокий приоритет"
3. Fill: `#FFC107` (warning, желтый)
4. Сгруппируй → назови `Badge / Row / Priority`

**Перетащи обе строки в Badge Bar**

**Переименуй:** `Badge / Bar`

**Проверь:** Badge bar с 2 строками, статусы сверху, приоритет снизу

---

## ШАГ 6: Создай MAIN CONTENT AREA (3 колонки)

**Что это:** Основной контент в 3 колонки

**Действия:**
1. Выбери frame → добавь Rectangle (`R`)
2. Размеры: 1408×auto
3. Fill: `transparent`
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Horizontal (→)
   - **Padding:** 0
   - **Gap:** 16 (расстояние между колонками)
   - **Alignment:** Top Stretch
   - **Distribution:** Fill (заполнить по ширине)

**Создай Left Column (6 cols):**
1. Выбери Main Content → добавь Rectangle
2. Fill: `#FFFFFF`
3. `Shift+A` → Auto Layout
4. Auto Layout настройки:
   - **Direction:** Vertical (↓)
   - **Padding:** 0
   - **Gap:** 16
   - **Alignment:** Top Stretch
5. В правой панели Layout → Fill container = `50%` (6 из 12 колонок)
6. Переименуй в: `Content / Column / Left`

**Создай Middle Column (4 cols):**
1. Дублируй Left Column (`Cmd+D`)
2. Fill container = `33%` (4 из 12 колонок)
3. Переименуй в: `Content / Column / Middle`

**Создай Right Column (2 cols):**
1. Дублируй Middle Column
2. Fill container = `17%` (2 из 12 колонок)
3. Переименуй в: `Content / Column / Right`

**Проверь:** 3 колонки с gap 16, пропорции 50% | 33% | 17%

---

## ШАГ 7: Заполни LEFF COLUMN (контент)

### 7.1 Создай блок "Описание заявки"

**Действия:**
1. Выбери Left Column → добавь Rectangle (`R`)
2. Размеры: 100%×auto
3. Fill: `#FFFFFF`
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Vertical (↓)
   - **Padding:** 16
   - **Gap:** 8
   - **Alignment:** Top Stretch

**Добавь заголовок:**
1. Текст (`T`): "Описание заявки"
2. Size: 14, Weight: 600, Color: #6C757D

**Добавь текст заявки:**
1. Текст (`T`): "Сломался кран в кухне..."
2. Size: 16, Weight: 400, Color: #212529
3. Multi-line: включи в текстовых настройках

**Добавь placeholder для "Дополнительные сведения":**
1. Текст (`T`): "(Дополнительные сведения)"
2. Size: 12, Weight: 400, Color: #6C757D
3. Скрой пока (можешь добавить потом)

**Сгруппируй всё → назови `Content / Block / Request Text`**

### 7.2 Создай блок "Решение"

**Действия:**
1. Скопируй "Request Text" блок
2. Переименуй в: `Content / Block / Resolution`
3. Измени заголовок на: "Решение"
4. Fill: `#D1E7DD` (Bootstrap success-bg, pale green)
5. Текст решения: "(Будет добавлено при завершении)"
6. Скрой пока (conditional block)

### 7.3 Создай блок "Жизненный цикл"

**Действия:**
1. Выбери Left Column → добавь Rectangle (`R`)
2. Размеры: 100%×auto
3. Fill: `#FFFFFF`
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Vertical (↓)
   - **Padding:** 16
   - **Gap:** 8
   - **Alignment:** Top Stretch

**Добавь заголовок:**
1. Текст: "Жизненный цикл"
2. Size: 14, Weight: 600, Color: #6C757D

**Добавь сетку для дат:**
1. Добавь Rectangle → `Shift+A` (Auto Layout)
2. Direction: Horizontal (→), Padding: 0, Gap: 16
3. Добавь 4 пары "Label: Value":
   - "Создана: 28.03.2026 14:30"
   - "Назначена: 28.03.2026 14:35"
   - "В работе с: 28.03.2026 15:00"
   - "Выполнена: —"
4. Каждую пару сделай как Auto Layout (Horizontal, Gap: 8)
5. Label текст: Size 12, Color #6C757D
6. Value текст: Size 14, Color #212529

**Сгруппируй всё → назови `Content / Block / Lifecycle`**

**Проверь:** Left Column с 3 блоками (Request, Resolution, Lifecycle), вертикальный gap 16

---

## ШАГ 8: Заполни MIDDLE COLUMN (timeline)

**Действия:**
1. Выбери Middle Column → добавь Rectangle (`R`)
2. Размеры: 100%×auto
3. Fill: `#F8F9FA` (серый фон)
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Vertical (↓)
   - **Padding:** 16
   - **Gap:** 16
   - **Alignment:** Top Stretch

**Добавь заголовок:**
1. Текст: "История событий"
2. Size: 16, Weight: 600, Color: #212529

**Создай Timeline Item (шаблон):**
1. Добавь Rectangle → `Shift+A`
2. Fill: `#FFFFFF`
3. Corner radius: 4
4. `Shift+A` → Auto Layout (Vertical, Padding: 12, Gap: 4)
5. Добавь элементы:
   - Timestamp: "28.03.2026 15:00" (Size 12, Color #6C757D)
   - Author + Text: "Иванов И.И.: Начато выполнение" (Size 14)
   - Badge: "В работе" (копия Badge / Status / Current)
6. Сгруппируй → назови `Timeline / Item`

**Создай 3-5 timeline items:**
1. Дублируй Timeline Item (`Cmd+D`) 3-5 раз
2. Измени данные в каждом:
   - Item 1: "28.03.2026 15:00 | Иванов И.И.: Начато выполнение | В работе"
   - Item 2: "28.03.2026 14:35 | System: Назначена на Петрова П.П. | Принята исполнителем"
   - Item 3: "28.03.2026 14:30 | System: Заявка зарегистрирована | Новая"

**Сгруппируй все timeline items → назови `Sidebar / Timeline`**

**Проверь:** Middle Column с заголовком + 3-5 timeline items, вертикальный gap 16

---

## ШАГ 9: Заполни RIGHT COLUMN (метрики)

**Действия:**
1. Выбери Right Column → добавь Rectangle (`R`)
2. Размеры: 100%×auto
3. Fill: `#FFFFFF`
4. `Shift+A` → Auto Layout
5. Auto Layout настройки:
   - **Direction:** Vertical (↓)
   - **Padding:** 16
   - **Gap:** 16
   - **Alignment:** Top Stretch

**Создай Metrics Rows:**

**Row 1 — Услуга:**
1. Добавь текст: "Услуга" (Size 12, Color #6C757D)
2. Добавь текст: "Сантехнические работы" (Size 14, Color #212529)
3. Сгруппируй → `Metrics / Row / Service`

**Row 2 — Подразделение:**
1. Текст: "Подразделение" → "Сантехническая служба"
2. Сгруппируй → `Metrics / Row / Department`

**Row 3 — Исполнитель:**
1. Текст: "Исполнитель" → "Петров П.П." (или "Не назначен")
2. Сгруппируй → `Metrics / Row / Responsible`

**Создай Technical Block (collapsible placeholder):**
1. Добавь Rectangle → `Shift+A`
2. Fill: `#F8F9FA`
3. Corner radius: 4
4. `Shift+A` → Auto Layout (Vertical, Padding: 12, Gap: 8)
5. Добавь заголовок: "Техническая информация [▼]" (Size 12, Weight: 600)
6. Добавь collapsed content:
   - "ID: #12345" (Size 12, Color #6C757D)
   - "Source: Бот (JSON)" (Size 12, Color #6C757D)
   - "Test: Нет" (Size 12, Color #6C757D)
7. Сгруппируй → `Metrics / Block / Technical`

**Перетащи всё в Right Column**

**Проверь:** Right Column с 3 metrics rows + 1 technical block

---

## ШАГ 10: Создай MODAL для "Завершить выполнение"

**Что это:** Модальное окно с полем "Текст решения"

**Действия:**
1. Нажми `+` → Frame (не Rectangle!)
2. Размеры: 600×auto
3. Fill: `#FFFFFF`
4. Corner radius: 8
5. `Shift+A` → Auto Layout (Vertical, Padding: 24, Gap: 16)

**Добавь заголовок:**
1. Текст: "Завершить выполнение заявки"
2. Size: 18, Weight: 600

**Добавь поле для ввода:**
1. Добавь Rectangle (placeholder для textarea)
2. Размеры: 552×120 (600 - 24×2 padding)
3. Fill: `#FFFFFF`
4. Stroke: `#DEE2E6` (Bootstrap border), Width: 1
5. Corner radius: 4
6. Текст-подсказка: "Опишите, что было сделано..." (Size 14, Color #6C757D)
7. Сгруппируй → `Modal / Field / Resolution`

**Добавь кнопки в footer:**
1. Создай Auto Layout (Horizontal, Gap: 8, Alignment: Right)
2. Кнопка "Отмена": Rectangle 80×40, Fill #6C757D (secondary)
3. Кнопка "Завершить": Rectangle 120×40, Fill #0D6EFD (primary)
4. Сгруппируй → `Modal / Footer`

**Сгруппируй всё → назови `Modal / Complete`**

**Проверь:** Modal с заголовком, полем ввода, 2 кнопками

---

## ШАГ 11: Проверь Auto Layout и отступы

**Действия:**
1. Выбери frame (самый верхний уровень)
2. Проверь в правой панели:
   - Auto Layout: Vertical (↓)
   - Padding: 16
   - Gap: 16
   - Alignment: Top Left

**Проверь структуру:**
```
Frame (1440×900)
├─ Header / Bar (56px)
├─ Action / Bar (64px)
├─ Badge / Bar (auto, 2 rows)
└─ Main Content (3 columns)
   ├─ Left Column (50%)
   │  ├─ Content / Block / Request
   │  ├─ Content / Block / Resolution
   │  └─ Content / Block / Lifecycle
   ├─ Middle Column (33%)
   │  └─ Sidebar / Timeline (3-5 items)
   └─ Right Column (17%)
      ├─ Metrics / Row / Service
      ├─ Metrics / Row / Department
      ├─ Metrics / Row / Responsible
      └─ Metrics / Block / Technical
```

**Проверь отступы:**
- Header: Padding 16, Gap 8
- Action Bar: Padding 16, Gap 8
- Badge Bar: Padding 0, Gap 8
- Main Content: Gap 16 (между колонками)
- Left Column: Gap 16 (между блоками)
- Middle Column: Padding 16, Gap 16
- Right Column: Padding 16, Gap 16

---

## ШАГ 12: Добавь placeholder для иконок (опционально)

**Что нужно:** Иконки для кнопок (Bootstrap Icons)

**Действия:**
1. Для каждой кнопки (Take, Start, Complete) добавь placeholder:
   - Текст: "[icon]" перед текстом кнопки
   - Или скопируй SVG иконки из Bootstrap Icons
   - bi-hand-index-thumb для Take
   - bi-play-circle для Start
   - bi-check-circle для Complete

**Простой способ (без SVG):**
1. Добавь текст `[icon]` перед каждой кнопкой
2. Size: 14, Color: #FFFFFF
3. Пример: "[icon] Взять заявку в работу"

**Правильный способ (с SVG):**
1. Скачай Bootstrap Icons SVG
2. Импортируй в Figma
3. Добавь перед текстом кнопки

---

## ШАГ 13: Проверь цвета (Bootstrap 5 tokens)

**Действия:**
1. Проверь цвета всех элементов:

**Header / Bar:**
- Background: #FFFFFF
- Text: #6C757D
- Emergency badge: #DC3545

**Action / Bar:**
- Background: #F8F9FA
- Button Take: #198754 (success, green)
- Button Start: #0D6EFD (primary, blue)
- Button Complete: #0D6EFD (primary, blue)
- Status badge: #0D6EFD

**Badge / Bar:**
- Internal status: #0D6EFD (primary)
- External status: #0DCAFE (info)
- Priority badge: #FFC107 (warning) / #DC3545 (danger)

**Content / Blocks:**
- Background: #FFFFFF
- Resolution block: #D1E7DD (success-bg, pale green)
- Labels: #6C757D (muted)
- Values: #212529 (dark)

**Sidebar / Timeline:**
- Background: #F8F9FA
- Item background: #FFFFFF
- Timestamp: #6C757D

**Modal:**
- Background: #FFFFFF
- Border: #DEE2E6
- Button Cancel: #6C757D (secondary)
- Button Complete: #0D6EFD (primary)

---

## ШАГ 14: Проверь размеры текста (Bootstrap tokens)

**Действия:**
1. Проверь размеры текста:

**Headers:**
- Page title (breadcrumb): 14px / 400 / #6C757D
- Block title (h6): 14px / 600 / #6C757D
- Section title (h5): 16px / 600 / #212529

**Body:**
- Primary text: 16px / 400 / #212529
- Secondary text: 14px / 400 / #212529
- Muted text: 12px / 400 / #6C757D

**Buttons:**
- Button text: 14px / 500 / #FFFFFF

**Badges:**
- Badge text: 12-14px / 500-600 / #FFFFFF

**Timeline:**
- Timestamp: 12px / 400 / #6C757D
- Event text: 14px / 400 / #212529

---

## ШАГ 15: Тест адаптивности (Tablet / Mobile)

**Что нужно:** Проверить, как экран выглядит на разных размерах

**Desktop (≥992px):**
- 3 колонки: 50% | 33% | 17%
- Header, Action Bar, Badge Bar на полную ширину

**Tablet (768px - 992px):**
- Collapse Right Column в Middle Column
- 2 колонки: 60% | 40%

**Mobile (<768px):**
- Stack всё вертикально
- 1 колонка: 100%

**Как протестировать:**
1. Выбери frame
2. В правой панели → нажми на иконку "responsive"
3. Выбери preset: Desktop, Tablet, Mobile
4. Проверь, что всё читаемо

**Для v1 можно пропустить:** Сделай только Desktop версию

---

## ШАГ 16: Сохраняй и экспортируй

**Действия:**
1. Проверь весь экран (Ctrl+0 / Cmd+0 чтобы fit to screen)
2. Проверь структуру в Layers panel
3. Сохрани: `Cmd+S` / `Ctrl+S`
4. Сделай скриншот: Export → PNG (1x, 2x)

**Проверь в Layers panel:**
- Frame "Work Order / Detail / Operator"
- Все блоки названы правильно
- Нет unnamed слоев
- Все Auto Layout настроены

---

## CHECKPOINTS (5 быстрых проверок)

**✅ Checkpoint 1: Auto Layout**
- Frame имеет Auto Layout (Vertical)
- Header, Action Bar, Badge Bar имеют Auto Layout
- Main Content имеет Auto Layout (Horizontal)
- 3 колонки имеют Auto Layout (Vertical)

**✅ Checkpoint 2: Отступы**
- Padding: 16px везде (кроме Header/Action Bar)
- Gap: 8px между элементами, 16px между блоками
- Header Bar height: 56px
- Action Bar height: 64px

**✅ Checkpoint 3: Цвета**
- Primary: #0D6EFD (синий)
- Success: #198754 (зеленый)
- Info: #0DCAFE (голубой)
- Warning: #FFC107 (желтый)
- Danger: #DC3545 (красный)

**✅ Checkpoint 4: Текст**
- Размеры: 12px (muted), 14px (body), 16px (section), 18px (modal title)
- Цвета: #212529 (dark), #6C757D (muted), #FFFFFF (on colored)
- Межстрочный интервал: 1.5 (по умолчанию)

**✅ Checkpoint 5: Структура**
- 3 колонки: Left (50%) | Middle (33%) | Right (17%)
- Left Column: Request + Resolution + Lifecycle
- Middle Column: Timeline (3-5 items)
- Right Column: 3 metrics rows + Technical block

---

## NEXT_FOR_CHATGPT

**Prompt для следующего шага (Django implementation):**

```
Я собрал Figma экран WorkOrder Detail Operator по build steps:
- File: tmp_archive/work_order_detail_operator_figma_layout_plan.md
- Build steps: tmp_archive/work_order_detail_operator_figma_build_steps.md
- Figma URL: https://www.figma.com/design/C7LCmH1rUjeuqqjcwMDZvb/Komunalka---WorkOrder-UI?node-id=1-2

Следующий шаг: Django template implementation.

Создай новый template work_order_detail_operator.html по Figma:
1. Используй Bootstrap 5 + 3-column grid (col-lg-6 | col-lg-4 | col-lg-2)
2. Следуй структуре: Header → Action Bar → Badge Bar → 3-Column Content
3. Реализуй все primary поля из contract (profile: detail_operator)
4. Скрой deferred actions (pause/resume)
5. Используй существующий timeline pattern
6. Добавь modal для complete_work_order

Sources:
- Form contract: tmp_archive/work_order_contract_v0.2_normalized.yaml
- Layout plan: tmp_archive/work_order_detail_operator_figma_layout_plan.md
- Build steps: tmp_archive/work_order_detail_operator_figma_build_steps.md
- Current template: work_orders/templates/work_orders/work_order_detail.html
```

---

**END OF BUILD STEPS**
**Created:** 2026-03-29
**Author:** Claude (Figma Build Instructor for Beginners)
**Status:** READY FOR MANUAL FIGMA ASSEMBLY
