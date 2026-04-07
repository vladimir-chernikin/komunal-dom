# SKILL: Figma + Django UI Workflow

**Назначение:** Workflow для перестройки Django UI по form contract и Figma дизайну.

**Scope:** Server-rendered Django + Bootstrap 5 + Figma MCP.

**Контекст:**
- Источник структуры экрана → form contract (YAML в tmp_archive/)
- Источник визуальной компоновки → Figma design
- Источник бизнес-логики → Django code (views, forms, models, admin)
- Профили экранов: detail_operator, detail_full, create

---

## АЛГОРИТМ РАБОТЫ

### ШАГ 1. ПРИНЯТЬ INPUT

**Обязательные input:**
1. **Form contract** — путь к YAML файлу в tmp_archive/
2. **Figma context** — URL или node ID дизайна
3. **Текущий Django экран** — template/view/admin для анализа

**Проверка input:**
- ✅ Form contract существует
- ✅ Figma design доступен
- ✅ Django файлы существуют

**ЕСЛИ чего-то не хватает:**
- Предупредить пользователя
- Предложить план сбора недостающего
- НЕ останавливать работу жестко

---

### ШАГ 2. АНАЛИЗИРОВАТЬ FORM CONTRACT

**Что искать:**
- `screen.code` — код экрана
- `screen.profiles` — доступные профили (detail_operator, detail_full, create)
- `fields` — список полей с метаданными
- Для каждого поля:
  - `source` — откуда берется (model|derived|relation)
  - `importance` — primary|secondary|technical|hidden_by_default
  - `editable` — можно ли редактировать
  - `backend_status` — реализовано или нет

**Проверка:**
- Понять, какой профиль используется
- Какие поля входят в профиль
- Какие поля редактируемые

---

### ШАГ 3. АНАЛИЗИРОВАТЬ FIGMA DESIGN

**Что искать:**
- Компоновка экрана (layout)
- Группировка полей (fieldsets, sections)
- Визуальная иерархия (что главное, что второстепенное)
- Интерактивные элементы (кнопки, действия)

**Интеграция с Figma MCP:**
- Использовать `get_design_context` для получения дизайна
- Использовать `get_screenshot` для визуального контекста
- НЕ использовать `use_figma` (это для записи в Figma)

**Проверка:**
- Соответствует ли дизайн form contract?
- Есть ли поля в дизайне, которых нет в contract?
- Есть ли поля в contract, которых нет в дизайне?

---

### ШАГ 4. АНАЛИЗИРОВАТЬ ТЕКУЩИЙ DJANGO КОД

**Что читать:**
- **Template** — `.html` файл для custom UI
- **View** — `.py` файл для бизнес-логики
- **Form** — `.py` файл для валидации (если есть)
- **Admin** — `.py` файл для Django admin (если используется)

**Проверка:**
- Какие поля отображаются?
- Какие поля редактируются?
- Какая группировка используется?
- Есть ли расхождения с form contract?

---

### ШАГ 5. СОСТАВИТЬ DIFF-PLAN

**НЕ менять код сразу! СНАЧАЛА показать plan!**

**Структура plan:**
```markdown
## ПЛАН ПЕРЕСТРОЙКИ ЭКРАНА [SCREEN_CODE]

### АНАЛИЗ РАСХОЖДЕНИЙ

**Form contract vs Figma design:**
- [+] Поля, которые есть в contract и design
- [-] Поля, которые есть в contract, но НЕТ в design
- [?] Поля, которые есть в design, но НЕТ в contract

**Form contract vs Django code:**
- [+] Поля, которые реализованы
- [-] Поля, которые НЕ реализованы
- [?] Поля, которые реализованы, но отличаются от contract

### ПЛАН ИЗМЕНЕНИЙ

**Файлы, которые будут затронуты:**
1. `path/to/template.html` — изменить компоновку
2. `path/to/view.py` — изменить логику (если нужно)
3. `path/to/admin.py` — изменить fieldsets (если это admin)

**Детальные изменения:**
- Секция 1: что менять
- Секция 2: что менять
- ...

### РИСКИ

- **Риск 1:** описание риска + план mitigiation
- **Риск 2:** описание риска + план mitigiation

### ПОСЛЕДУЮЩИЕ ШАГИ

1. Показать этот plan пользователю
2. Получить подтверждение
3. Внести изменения
4. Перезапустить gunicorn (если менялись .py файлы)
5. Проверить результат
```

---

### ШАГ 6. ПОЛУЧИТЬ ПОДТВЕРЖДЕНИЕ

**ОБЯЗАТЕЛЬНО:**
- Показать plan пользователю
- Дождаться подтверждения
- НЕ вносить изменения без подтверждения

**Если пользователь не согласен:**
- Обсудить альтернативы
- Изменить plan
- Повторить подтверждение

---

### ШАГ 7. ВНЕСТИ ИЗМЕНЕНИЯ

**ПОСЛЕ подтверждения:**

1. **Изменить template:**
   - Обновить компоновку согласно Figma design
   - Обновить поля согласно form contract
   - Сохранить существующие паттерны (Bootstrap 5)

2. **Изменить view/admin (если нужно):**
   - Обновить fieldsets
   - Обновить логику отображения
   - Сохранить бизнес-логику

3. **Установить права доступа:**
   ```bash
   chmod 644 template.html
   chown olga:www-data template.html
   ```

4. **Перезапустить gunicorn (если менялись .py файлы):**
   ```bash
   systemctl restart gunicorn-komunal-dom
   systemctl status gunicorn-komunal-dom
   ```

---

### ШАГ 8. ПРОВЕРИТЬ РЕЗУЛЬТАТ

**Проверки:**
- ✅ Файлы созданы/изменены
- ✅ Права доступа установлены
- ✅ Gunicorn перезапущен (если нужно)
- ✅ Страница доступна (curl -I)

**Если есть ошибки:**
- Диагностировать проблему
- Исправить
- Повторить проверки

---

## ЧТО SKILL НЕ ДЕЛАЕТ

- ❌ НЕ меняет models.py (это DB schema, не UI)
- ❌ НЕ меняет бизнес-логику без явного указания
- ❌ НЕ автоматически синхронизирует metadata и template
- ❌ НЕ делает mass refactoring
- ❌ НЕ меняет другие экраны кроме указанного
- ❌ НЕ использует `use_figma` (только чтение из Figma)

---

## ПРЕДОХРАНИТЕЛИ

**ЕСЛИ metadata и template расходятся:**
- ❌ НЕ редактировать автоматически без явного указания
- ✅ Показать расхождение в plan
- ✅ Предложить варианты решения
- ✅ Дождаться явного указания пользователя

**ЕСЛИ form contract не существует:**
- ⚠️ Предупреждение: "Form contract не найден"
- ✅ Предложить создать contract
- ✅ НЕ останавливать работу, если пользователь хочет продолжить

**ЕСЛИ Figma design не доступен:**
- ⚠️ Предупреждение: "Figma design не доступен"
- ✅ Предоставить работу по form contract только
- ✅ НЕ останавливать работу

---

## WorkOrder СПЕЦИФИКА

**Профили:**
- `detail_operator` — Custom UI для исполнителей (усеченный набор полей)
- `detail_full` — Django Admin для администраторов (полный набор)
- `create` — Форма создания (5 полей)

**Файлы:**
- Template: `work_orders/templates/work_orders/work_order_detail.html`
- View: `work_orders/views.py:WorkOrderDetailView`
- Admin: `work_orders/admin.py:WorkOrderAdmin`

**Contract:**
- `tmp_archive/work_order_contract_v0.2_normalized.yaml`

---

## ИНТЕГРАЦИЯ С HOOKS

**Pre-hook:** `ui_change_pre_check.md`
- Запускается ПЕРЕД UI-изменениями
- Проверяет наличие form contract
- Проверяет какие файлы будут затронуты

**Post-hook:** `ui_change_post_check.md`
- Запускается ПОСЛЕ UI-изменений
- Выполняет безопасные проверки
- Запускает `python manage.py check` (если возможно)

---

## КОНТРОЛЬНЫЙ СПИСОК ПЕРЕД ВЫПОЛНЕНИЕМ

- [ ] Я принял form contract?
- [ ] Я принял Figma context?
- [ ] Я принял текущий Django экран?
- [ ] Я показал diff-plan пользователю?
- [ ] Я получил подтверждение?
- [ ] Я установил права на файлы?
- [ ] Я перезапустил gunicorn (если нужно)?
- [ ] Я проверил результат?

**ЕСЛИ ХОТЬ ОДИН "НЕТ" - ОСТАНОВИТЬСЯ!**

---

## ПРИМЕРЫ РАБОТЫ

### ПРИМЕР 1: Анализ WorkOrder экрана

```
User: "проанализируй экран WorkOrder для detail_operator"

Skill:
1. Читает: tmp_archive/work_order_contract_v0.2_normalized.yaml
2. Извлекает поля для profile: detail_operator
3. Читает: work_orders/templates/work_orders/work_order_detail.html
4. Анализирует расхождения
5. Показывает plan изменений
```

### ПРИМЕР 2: Figma-oriented layout plan

```
User: "подготовь Figma-oriented layout plan для WorkOrder"

Skill:
1. Читает form contract
2. Использует get_design_context для Figma design
3. Сопоставляет поля в contract и design
4. Группирует поля по секциям
5. Показывает plan компоновки
```

### ПРИМЕР 3: Перестройка Django UI

```
User: "перестрой Django UI по form contract и Figma, но сначала покажи plan"

Skill:
1. Читает form contract
2. Получает Figma context
3. Анализирует текущий Django код
4. Показывает diff-plan
5. Ждет подтверждения
6. Вносит изменения (после подтверждения)
7. Устанавливает права
8. Перезапускает gunicorn
9. Проверяет результат
```

---

**ПРИНЦИП:** Skill = expert по workflow Django form metadata → Figma → Claude → Django UI.
