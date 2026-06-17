# СХЕМА БАЗЫ ДАННЫХ services_catalog

## Обзор

Документация структуры БД для системы определения услуг через воронку точности.

**Дата:** 2025-12-23
**Версия:** 1.0

---

## Основная таблица: services_catalog

### Структура

| Колонка | Тип | Обязательный | Описание |
|---------|-----|-------------|-----------|
| `service_id` | integer | ✅ | PK, Auto increment |
| `scenario_id` | varchar(20) | ✅ | Уникальный ID сценария |
| `scenario_name` | varchar(255) | ✅ | Название услуги **для поиска** |
| `type_id` | smallint | ✅ | FK → ref_service_types.type_id |
| `kind_id` | smallint | ✅ | FK → ref_service_kinds.kind_id |
| `localization_id` | smallint | ✅ | FK → ref_localization.localization_id |
| `category_id` | smallint | ✅ | FK → ref_categories.category_id |
| `object_id` | smallint | ✅ | FK → ref_objects.object_id |
| `payment_id` | smallint | ✅ | FK → ref_payment_status.payment_id |
| `route_id` | smallint | ✅ | FK → ref_routes.route_id |
| `urgency_id` | smallint | ✅ | FK → ref_urgency.urgency_id |
| `description_for_search` | text | ❌ | Описание для поиска |
| `is_active` | boolean | ❌ | Активна ли услуга (default: true) |
| `created_at` | timestamp | ❌ | Дата создания |
| `updated_at` | timestamp | ❌ | Дата обновления |

### Важно!

**`scenario_name`** - это основное поле для поиска услуг!
- Используется во всех микросервисах
- Отображается пользователю
- Должно быть понятным и описательным

**НЕ используйте эти колонки** (их не существует!):
- ❌ `incident_type`
- ❌ `category`
- ❌ `object_type`
- ❌ `location_type`

Вместо них используйте **JOIN к ref таблицам**:
- ✅ `type_name` из `ref_service_types`
- ✅ `category_name` из `ref_categories`
- ✅ `object_name` из `ref_objects`
- ✅ `localization_name` из `ref_localization`

---

## Справочные таблицы (ref_*)

### ref_service_types

Типы услуг (Инцидент/Запрос)

| Колонка | Описание |
|---------|----------|
| `type_id` (PK) | ID типа |
| `type_code` | Код (INCIDENT/REQUEST) |
| `type_name` | **Название типа** |

**Значения:**
- 13 → INCIDENT → Инцидент
- 14 → REQUEST → Запрос

---

### ref_categories

Категории услуг

| Колонка | Описание |
|---------|----------|
| `category_id` (PK) | ID категории |
| `category_code` | Код категории |
| `category_name` | **Название категории** |

**Примеры:**
- Электричество
- Конструктив
- Озеленение
- Санитария
- Ремонт МАФ и покрытий

**Триграммный индекс:** `idx_ref_categories_category_name_trgm` ✅

---

### ref_objects

Объекты обслуживания

| Колонка | Описание |
|---------|----------|
| `object_id` (PK) | ID объекта |
| `object_code` | Код объекта |
| `object_name` | **Название объекта** |
| `is_common` | Общедомовое имущество? |

**Примеры:**
- Квартира
- Двор
- Подъезд
- Крыша
- Лифт

**Триграммный индекс:** `idx_ref_objects_object_name_trgm` ✅

---

### ref_localization

Локализация услуг

| Колонка | Описание |
|---------|----------|
| `localization_id` (PK) | ID локализации |
| `localization_code` | Код |
| `localization_name` | Название |

---

### ref_service_kinds

Виды услуг

| Колонка | Описание |
|---------|----------|
| `kind_id` (PK) | ID вида |
| `kind_code` | Код |
| `kind_name` | Название |

**Примеры:**
- Стандартный
- Аварийный
- Плановый

---

### ref_tags

Теги для поиска услуг

| Колонка | Описание |
|---------|----------|
| `tag_id` (PK) | ID тега |
| `tag_name` | **Название тега** |
| `tag_category` | Категория тега |
| `weight_coefficient` | Весовой коэффициент |
| `is_active` | Активен ли? |

**Триграммный индекс:** `idx_ref_tags_name_trgm` ✅

---

## Таблица связей: service_tags

### Структура

| Колонка | Тип | Описание |
|---------|-----|----------|
| `service_tag_id` | integer | PK |
| `service_id` | integer | FK → services_catalog.service_id |
| `tag_id` | integer | FK → ref_tags.tag_id |
| `tag_weight` | numeric(3,2) | Вес тега (default: 1.00) |

### Индексы

- `idx_service_tags_service_id` на `service_id`
- `idx_service_tags_tag_id` на `tag_id`
- `idx_service_tags_weight` на `tag_weight DESC`

**Связей:** 372

---

## Триграммные индексы (pg_trgm)

### Что это?

Триграммные индексы PostgreSQL для нечеткого поиска текста. Используют расширение `pg_trgm`.

### Существующие индексы

| Таблица | Колонка | Индекс | Статус |
|---------|---------|---------|--------|
| `services_catalog` | `scenario_name` | `idx_services_catalog_scenario_name_trgm` | ✅ |
| `services_catalog` | `description_for_search` | `idx_services_catalog_description_trgm` | ✅ |
| `ref_tags` | `tag_name` | `idx_ref_tags_name_trgm` | ✅ |
| `ref_categories` | `category_name` | `idx_ref_categories_category_name_trgm` | ✅ |
| `ref_objects` | `object_name` | `idx_ref_objects_object_name_trgm` | ✅ |
| `buildings` | `house_number` | `idx_buildings_house_number_trgm` | ✅ |
| `kladr_address_objects` | `name` | `idx_kao_name_trgm` | ✅ |

### SQL функции для поиска

```sql
-- Точное совпадение по триграммам
word_similarity(text, column) > 0.3

-- Нечеткий поиск
text % column  -- оператор похожести
```

---

## Примеры SQL запросов

### Правильный запрос с JOIN к ref таблицам

```sql
SELECT
    sc.service_id,
    sc.scenario_name,
    sc.description_for_search,
    rt.type_name,           -- ✅ ИСПРАВЛЬНО
    rst.kind_name,
    rc.category_name,       -- ✅ ИСПРАВЛЬНО
    ro.object_name,         -- ✅ ИСПРАВЛЬНО
    rl.localization_name
FROM services_catalog sc
LEFT JOIN ref_service_types rt ON sc.type_id = rt.type_id
LEFT JOIN ref_service_kinds rst ON sc.kind_id = rst.kind_id
LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
LEFT JOIN ref_objects ro ON sc.object_id = ro.object_id
LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
WHERE sc.is_active = TRUE
```

### ❌ НЕПРАВИЛЬНЫЙ запрос

```sql
SELECT
    sc.service_id,
    sc.incident_type,      -- ❌ ТАКОЙ КОЛОНКИ НЕТ!
    sc.category,           -- ❌ ТАКОЙ КОЛОНКИ НЕТ!
    sc.object_type,        -- ❌ ТАКОЙ КОЛОНКИ НЕТ!
    sc.location_type       -- ❌ ТАКОЙ КОЛОНКИ НЕТ!
FROM services_catalog sc
```

---

## Статистика БД

| Метрика | Значение |
|---------|----------|
| Активных услуг | 68 |
| Всех услуг | 68 |
| Связей service_tags | 372 |
| Активных тегов | 348 |
| Категорий | 13 |
| Объектов | 10 |
| Триграммных индексов | 7 |

---

## Unit-тесты

Для проверки структуры БД используйте:

```bash
python /var/www/komunal-dom_ru/tests/test_db_schema.py
```

Тесты проверяют:
- Наличие всех колонок в services_catalog
- Наличие ref таблиц
- Наличие *_name колонок в ref таблицах
- Наличие внешних ключей
- Наличие триграммных индексов
- Целостность данных
- Структуру service_tags

---

## Частые ошибки

### 1. Использование несуществующих колонок

**Ошибка:**
```python
service_info.get('incident_type')  # ❌ None
```

**Исправление:**
```python
service_info.get('type_name')  # ✅ 'Инцидент' или 'Запрос'
```

### 2. Забыл JOIN к ref таблицам

**Ошибка:**
```python
# Загружаем только ID
cursor.execute("""
    SELECT service_id, scenario_name, type_id, category_id
    FROM services_catalog
""")
```

**Исправление:**
```python
# Загружаем с JOIN
cursor.execute("""
    SELECT sc.service_id, sc.scenario_name,
           rt.type_name, rc.category_name
    FROM services_catalog sc
    LEFT JOIN ref_service_types rt ON sc.type_id = rt.type_id
    LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
""")
```

---

## Изменения

| Дата | Версия | Описание |
|------|--------|----------|
| 2025-12-23 | 1.0 | Первая версия документации |
