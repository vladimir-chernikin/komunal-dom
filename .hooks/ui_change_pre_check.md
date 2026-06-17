# HOOK: UI Change Pre-Check

**Назначение:** Проверка перед UI-изменениями в Django проекте.

**Приоритет:** Высокий (срабатывает перед любыми изменениями templates/views/forms/admin).

---

## КОГДА СРАБАТЫВАЕТ

Hook срабатывает при обнаружении любых из этих паттернов:

### Изменение templates:
- Редактирование `.html` файлов в `*/templates/`
- Изменение Django templates
- Изменение компоновки экрана

### Изменение views:
- Редактирование `views.py` с упоминанием specific screens (WorkOrder, etc.)
- Изменение логики отображения

### Изменение forms:
- Редактирование `forms.py`
- Добавление/изменение полей формы

### Изменение admin:
- Редактирование `admin.py`
- Изменение fieldsets
- Изменение list_display

### Явные запросы пользователя:
- "измени интерфейс"
- "обнови экран"
- "перестрой template"
- "измени компоновку"
- "обнови Figma design"
- "синхронизируй UI с контрактом"

---

## КОГДА НЕ СРАБАТЫВАЕТ

- ❌ Изменение models.py (это DB schema, не UI)
- ❌ Изменение business logic без UI impact
- ❌ Runtime операции (gunicorn, nginx)
- ❌ Работа с git, файлами, директориями
- ❌ Чтение templates без намерения изменять

---

## ЧТО ДЕЛАЕТ HOOK

1. **ПРОВЕРЯЕТ наличие form contract:**
   - Ищет YAML файл в `tmp_archive/`
   - Проверяет, что contract существует
   - Предупреждает, если contract не найден

2. **ПРОВЕРЯЕТ какие файлы будут затронуты:**
   - Template файл
   - View файл (если меняется логика)
   - Admin файл (если это admin экран)
   - Form файл (если есть)

3. **ПРОВЕРЯЕТ существование файлов:**
   - Template существует?
   - View существует?
   - Admin существует?
   - Form существует?

4. **НАПРАВЛЯЕТ в Skill:**
   - `figma_django_ui_workflow` для выполнения работы
   - НЕ выполняет бизнес-логику сам

5. **НЕ ЗАПРЕЩАЕТ работу:**
   - Если чего-то не хватает — предупреждает, но НЕ останавливает
   - Если пользователь хочет продолжить — позволяет

---

## ПРЕДОХРАНИТЕЛИ

**ЕСЛИ form contract не существует:**
- ⚠️ Предупреждение: "Form contract не найден в tmp_archive/"
- ✅ Предложить создать contract
- ✅ Предложить продолжить без contract (если пользователь хочет)
- ❌ НЕ останавливать работу жестко

**ЕСЛИ template не существует:**
- ⚠️ Предупреждение: "Template не найден"
- ✅ Предложить создать template
- ✅ Предложить проверить путь
- ❌ НЕ останавливать работу жестко

**ЕСЛИ view/admin не существуют:**
- ⚠️ Предупреждение: "View/admin не найдены"
- ✅ Предоставить работу только с template
- ❌ НЕ останавливать работу жестко

---

## ТЕХНИЧЕСКИЕ ПРОВЕРКИ

**Проверка form contract:**
```bash
ls -la /var/www/komunal-dom_ru/tmp_archive/*contract*.yaml 2>/dev/null
```

**Проверка template:**
```bash
ls -la /var/www/komunal-dom_ru/work_orders/templates/work_orders/*.html
```

**Проверка view:**
```bash
ls -la /var/www/komunal-dom_ru/work_orders/views.py
```

**Проверка admin:**
```bash
ls -la /var/www/komunal-dom_ru/work_orders/admin.py
```

---

## ИНТЕГРАЦИЯ С SKILL

Hook всегда запускает Skill: `figma_django_ui_workflow`

**ПАТТЕРН:**
```
User: "измени интерфейс WorkOrder"
  ↓
Hook: Срабатывает (обнаружено изменение template)
  ↓
Hook: Проверяет form contract
  ↓
Hook: Проверяет файлы экрана
  ↓
Hook: Направляет в Skill figma_django_ui_workflow
  ↓
Skill: Выполняет работу
```

---

## КРИТИЧЕСКИЕ ПРАВИЛА

1. ✅ **ВСЕГДА** проверять form contract перед UI-изменениями
2. ✅ **ВСЕГДА** проверять какие файлы будут затронуты
3. ✅ **ВСЕГДА** направлять в Skill для выполнения работы
4. ✅ **ПРЕДУПРЕЖДАТЬ** если чего-то не хватает
5. ❌ **НЕ ЗАПРЕЩАТЬ** работу жестко
6. ❌ **НЕ ВЫПОЛНЯТЬ** бизнес-логику сам
7. ❌ **НЕ СОЗДАВАТЬ** файлы автоматически без указания

---

## WorkOrder СПЕЦИФИКА

**Form contract:**
- `tmp_archive/work_order_contract_v0.2_normalized.yaml`

**Файлы экрана:**
- Template: `work_orders/templates/work_orders/work_order_detail.html`
- View: `work_orders/views.py:WorkOrderDetailView`
- Admin: `work_orders/admin.py:WorkOrderAdmin`

**Профили:**
- detail_operator
- detail_full
- create

---

## ФОРМАТ ПРЕДУПРЕЖДЕНИЙ

**ЕСЛИ form contract не найден:**
```markdown
⚠️ ПРЕДУПРЕЖДЕНИЕ: Form contract не найден

Ожидалось: `tmp_archive/work_order_contract_v0.2_normalized.yaml`
Статус: Файл не существует

Варианты:
1. Создать form contract
2. Продолжить без contract (не рекомендуется)
3. Отменить операцию

Что делать?
```

**ЕСЛИ template не найден:**
```markdown
⚠️ ПРЕДУПРЕЖДЕНИЕ: Template не найден

Ожидалось: `work_orders/templates/work_orders/work_order_detail.html`
Статус: Файл не существует

Варианты:
1. Создать template
2. Проверить путь к файлу
3. Отменить операцию

Что делать?
```

---

**ПРИНЦИП:** Hook = триггер и маршрутизатор к Skill `figma_django_ui_workflow`.
