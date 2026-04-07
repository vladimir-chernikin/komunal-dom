# WORK ORDER CONTRACT v0.2 - NORMALIZATION SUMMARY

**Дата:** 2026-03-28
**Архитектор:** Claude (Senior Metadata-Driven UI Architect)
**Статус:** ГОТОВО К ИСПОЛЬЗОВАНИЮ

---

## 📋 ЧТО СДЕЛАНО

Создан **нормализованный metadata contract** для экрана WorkOrder, пригодный для конвейера:
```
Django code → YAML metadata → Figma → Claude → Django templates
```

### 3 созданных файла:

1. **work_order_contract_v0.2_normalized.yaml** (450 строк)
   - Полный metadata contract v0.2
   - Готов для использования в pipeline

2. **work_order_contract_v0.2_diff.md** (таблица изменений)
   - Сравнение: raw extraction vs normalized
   - Обоснование каждого изменения

3. **work_order_contract_v0.2_summary.md** (этот файл)
   - Краткое резюме для product owner

---

## 🎯 КЛЮЧЕВЫЕ АРХИТЕКТУРНЫЕ РЕШЕНИЯ

### 1. PROFILES вместо множественных screens

✅ **До**: 2 отдельных описания (Django Admin + Custom UI)
✅ **После**: 1 сущность с 3 профилями:
- `detail_operator` - Custom UI для исполнителей (15-20 полей)
- `detail_full` - Django Admin для администраторов (35+ полей)
- `create` - Форма создания (5 полей)

**Выгода**: Единое описание сцесущности, разные сценарии использования

---

### 2. SOURCE attribution

✅ Каждое поле явно помечено источником:
- `model` - поле существует в Django модели
- `derived` - вычисляемое поле
- `relation` - FK или related field
- `action_input` - поле только для ввода в action
- `system` - системное поле (created_at, updated_at)

**Выгода**: Четкое понимание происхождения данных, не гадаем

---

### 3. IMPORTANCE tiering

✅ Каждое поле имеет приоритет:
- `primary` - обязательно показать на первом экране
- `secondary` - показать на expanded view
- `technical` - техническое поле, скрыто по умолчанию
- `hidden_by_default` - вообще не показывать в UI

**Выгода**: UX приоритизация, не технические детали

---

### 4. Разделение правил: UI vs SERVER

✅ **ui_rules** - только визуальная логика:
- visible_when (показывать элемент?)
- enabled_when (элемент активен?)
- required_when (поле обязательно?)

✅ **server_rule_refs** - ссылки на Django code:
- permission guards
- DB constraints
- validation logic
- side effects

**Выгода**: Single source of truth в Django, metadata только для UI

---

### 5. ACTIONS KINDS

✅ Все действия классифицированы по UX паттерну:
- `inline_button` - кнопка на карточке
- `modal_submit` - кнопка, открывающая модал
- `page_action` - действие на уровне страницы

✅ **backend_status** - честно указываем:
- `implemented` - работает в Django (4 actions)
- `deferred` - планируется (2 actions: pause/resume)
- `excluded_from_v0_2` - не входит в v0.2

**Выгода**: Понятно, что можно использовать в UI, что нет

---

### 6. FIGMA MAPPING

✅ Добавлен раздел для дизайнеров:
- screen_frame_name
- tab_frames
- component_hints (typography, colors, spacing, components)
- density (dense)
- layout_pattern (operator_console)
- layout_structure (2 columns + sidebar)
- responsive_breakpoints

**Выгода**: Figma designer знает точные требования к layout

---

## 📊 КОЛИЧЕСТВЕННЫЕ МЕТРИКИ

| Метрика | Raw Extraction | Normalized v0.2 | Изменение |
|---------|----------------|-----------------|-----------|
| Строк на поле | 15-20 | 3-5 | **-75%** |
| Всего строк | ~800 | ~450 | **-44%** |
| Правил | 11 (смешанные) | 6 ui + 10 server | **Разделение** |
| Actions | 7 (однородные) | 4 impl + 2 deferred | **Честность** |
| Profiles | 0 | 3 | **Новое** |
| Figma hints | 0 | 50+ | **Новое** |

**Итого**: Компактнее, чище, пригоднее для реального использования

---

## 🔄 ГЛАВНЫЕ ИЗМЕНЕНИЯ

| Категория | Было | Стало | Почему |
|-----------|------|-------|--------|
| **STRUCTURE** | Монолитный YAML | Profiles: 3 сценария | Разные пользователи |
| **FIELD** | 15-20 строк/поле | 3-5 строк/поле | Убрать избыточность |
| **SOURCE** | Не указано | model/derived/relation/... | Понимание данных |
| **IMPORTANCE** | Неявно | primary/secondary/... | UX приоритизация |
| **RULES** | Смешано | ui_rules + server_rule_refs | UI ≠ бизнес-логика |
| **PERMS** | Дублированы | Только ссылки | Single source of truth |
| **ACTIONS** | Однородно | implemented/deferred | Честность |
| **FIGMA** | Не было | Полный mapping | Интеграция |
| **EXPORT** | Не было | automatic/manual | Понять процесс |

---

## 📂 ФАЙЛЫ ДЛЯ ДАЛЬНЕЙШЕЙ РАБОТЫ

### Обязательные (CORE)

1. **work_orders/models.py** (lines 550-748)
   - Модель WorkOrder с 35+ полями
   - Источник структуры данных

2. **work_orders/admin.py** (lines 106-151)
   - 6 fieldsets (вкладки)
   - Источник структуры экрана

3. **work_orders/views.py** (lines 134-153, 289-450)
   - WorkOrderDetailView
   - API endpoints (4 actions)
   - Permission guards

### Важные (IMPORTANT)

4. **work_orders/templates/work_orders/work_order_detail.html**
   - Custom UI реализация
   - Inline JavaScript для AJAX
   - visible_when правила (template-based)

5. **work_orders/templates/work_orders/work_order_create.html**
   - Форма создания (5 полей)
   - Bootstrap form widgets

6. **tmp_archive/work_order_contract_v0.2_normalized.yaml**
   - Нормализованный contract v0.2
   - Готов для использования

### Справочные (REFERENCE)

7. **tmp_archive/work_order_screen_analysis.md**
   - Полный анализ экрана (raw extraction)
   - 2500 строк кода проанализировано

8. **tmp_archive/work_order_contract_v0.2_diff.md**
   - Сравнение raw vs normalized
   - Обоснование изменений

---

## 🚀 СЛЕДУЮЩИЕ ШАГИ

### Ближайшие (1-2 недели)

1. **УТВЕРДИТЬ PROFILES**: Уточнить с product owner, нужно ли 3 профиля
2. **РЕШИТЬ PAUSE/RESUME**: Реализовать backend или убрать из UI
3. **УТОЧНИТЬ IMPORTANCE**: Review с UX командой
4. **FIGMA INTEGRATION**: Начать перенос в Figma

### Среднесрочные (1-2 месяца)

5. **SLA UI**: Решить, показывать ли SLA timers
6. **ATTACHMENT UI**: Реализовать загрузку фото
7. **JAVASCRIPT**: Extract inline JS в separate modules
8. **COMPONENT LIBRARY**: Создать reusable Figma components

### Долгосрочные (3-6 месяцев)

9. **METADATA ENGINE**: Разработать или выбрать framework
10. **DYNAMIC PROFILES**: Runtime switching между профилями
11. **RULES ENGINE**: Expressive rules для complex conditions
12. **FIGMA SYNC**: Двунаправленная синхронизация

---

## ✅ КРИТЕРИИ КАЧЕСТВА

Normalized YAML соответствует критериям:

- [x] **Компактнее**: 450 строк vs 800 (-44%)
- [x] **Чище**: 3-5 строк/поле vs 15-20 (-75%)
- [x] **Пригоднее**: Готов для Django → Figma → Claude pipeline
- [x] **Нет дублирования**: Single source of truth в Django code
- [x] **Честность**: Реально работающий код marked as implemented
- [x] **Разделение**: UI логика отдельно от бизнес-логики
- [x] **Интеграция**: Figma mapping для bidirectional sync
- [x] **Экспорт**: Понятно, что автоматическое, что manual

---

## 📞 КОНТАКТЫ

**Вопросы по metadata contract:**
- Архитектура: profiles, source attribution, rules separation
- Figma integration: component_hints, layout_pattern
- Export process: automatic vs manual

**Вопросы по реализации:**
- Django code: views.py, admin.py, models.py
- Actions: API endpoints, permission guards
- Validation: server_rule_refs

---

**КОНЕЦ SUMMARY**
