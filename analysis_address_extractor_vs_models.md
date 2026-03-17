# АНАЛИЗ: AddressExtractor и модели адресов

## 1. AddressExtractor - какую модель использует?

**ОТВЕТ:** AddressExtractor использует **СТАРУЮ модель адресов**

**Доказательства:**

```python
# old/service_detection_modules.py:1360
cursor.execute("""
    SELECT ao.ao_id, ao.name
    FROM kladr_address_objects ao  ← СТАРАЯ схема
    ...
""")

# old/service_detection_modules.py:1382
cursor.execute("""
    SELECT building_id
    FROM buildings  ← СТАРАЯ схема
    WHERE parent_ao_id = %s
    ...
""")
```

**Проблема:** service_detection_modules.py находится в папке `old/` и НЕ ИСПОЛЬЗУЕТСЯ в коде!

---

## 2. Проблема "Здание ID=8" - где исправлено?

**ОТВЕТ:** Исправлено ТОЛЬКО в **НОВОЙ схеме**

### СТАРАЯ схема (buildings, kladr_address_objects):

```sql
SELECT * FROM buildings WHERE building_id = 8;
-- building_id | house_number | street_name | kladr_level
-- -------------+--------------|-------------|-------------
--            8 | 21           | Сочи        | 2 (город) ❌
```

**Проблема:** Всё еще привязано к городу!

### НОВАЯ схема (kladr_building, kladr_kladraddressobject):

```sql
SELECT * FROM kladr_building WHERE id = 8;
-- id | house_number |    street_name    | level
-- ----+--------------|-------------------|-------
--  8 | 21           | Ворошиловградская | 5 (улица) ✅
```

**Исправлено:** Привязано к улице!

---

## 3. Использование схем в коде

### bot_service_requests (заявки):
- `building_id` → **buildings** (СТАРАЯ)
- Используется: **1 заявка** (building_id=1)

### units (квартиры):
- `building_id` → **buildings** (СТАРАЯ)
- Используется: **2612 квартир** ❌

### Веб-интерфейс:
- `portal/views.py` → **kladr.models** (НОВАЯ) ✅
- `portal/kladr_views.py` → **kladr.models** (НОВАЯ) ✅
- `portal/admin_views.py` → **kladr.models** (НОВАЯ) ✅

### AddressExtractor:
- Файл: `old/service_detection_modules.py`
- Использует: **kladr_address_objects**, **buildings** (СТАРАЯ) ❌
- Статус: **НЕ ИСПОЛЬЗУЕТСЯ** (файл в `old/`)

---

## 4. КРИТИЧЕСКАЯ ПРОБЛЕМА

### Проблема раздвоения:

```
AddressExtractor (СТАРАЯ модель)
    ↓
Ищет в buildings (СТАРАЯ)
    ↓
НЕ НАХОДИТ (потому что bot_service_requests → building_id → buildings)
    ↓
2612 квартир в units → buildings (СТАРАЯ) ❌

Параллельно:

kladr.models (НОВАЯ модель)
    ↓
kladr_building (НОВАЯ)
    ↓
58 зданий ✅
```

---

## 5. РЕКОМЕНДАЦИЯ: Какую модель оставить?

### ✅ ОСТАВИТЬ: НОВУЮ модель (kladr.models)

**Причины:**
1. ✅ Django ORM (удобно поддерживать)
2. ✅ Web-интерфейс (`/admin-uk/kladr/`)
3. ✅ Здание ID=8 исправлено ✅
4. ✅ Методы `get_full_address()`
5. ✅ Администрирование через Django admin
6. ✅ Миграции через Django

### ❌ УДАЛИТЬ: СТАРУЮ модель (kladr_address_objects, buildings)

**Причины:**
1. ❌ Прямые SQL запросы (сложно поддерживать)
2. ❌ Нет методов для полного адреса
3. ❌ Здание ID=8 НЕ исправлено ❌
4. ❌ Файл AddressExtractor в `old/` (не используется)
5. ❌ Дублирование данных ( те же 58 зданий)

---

## 6. ПЛАН МИГРАЦИИ

### Шаг 1: Перенести units на НОВУЮ модель

```sql
-- ОБНОВИТЬ units.building_id → kladr_building
UPDATE units u
SET building_id = kb.id
FROM kladr_building kb
JOIN kladr_kladraddressobject kko ON kb.address_object_id = kko.id
WHERE u.building_id = kb.id;
```

### Шаг 2: Перенести bot_service_requests на НОВУЮ модель

```sql
-- ОБНОВИТЬ bot_service_requests.building_id → kladr_building
UPDATE bot_service_requests bsr
SET building_id = kb.id
FROM kladr_building kb
WHERE bsr.building_id = kb.id;
```

### Шаг 3: Удалить СТАРУЮ модель

```sql
-- Удалить старые таблицы
DROP TABLE IF EXISTS buildings CASCADE;
DROP TABLE IF EXISTS kladr_address_objects CASCADE;
DROP TABLE IF EXISTS kladr_types CASCADE;
```

### Шаг 4: Обновить AddressExtractor

- Перенести `service_detection_modules.py` из `old/` в корень
- Заменить `kladr_address_objects` → `kladr_kladraddressobject`
- Заменить `buildings` → `kladr_building`

---

## 7. ИТОГОВАЯ ТАБЛИЦА

| Характеристика | Старая модель | Новая модель | Победитель |
|---|---|---|---|
| **Django ORM** | ❌ Нет | ✅ Да | Новая |
| **Web-интерфейс** | ❌ Нет | ✅ `/admin-uk/kladr/` | Новая |
| **Методы** | ❌ Нет | ✅ `get_full_address()` | Новая |
| **Здание ID=8** | ❌Broken | ✅Исправлено | Новая |
| **Использование** | 2613 records ❌ | 58 records | **Старая** (пока!) |
| **Поддержка** | ❌ Сложно | ✅ Легко | Новая |

---

## ВЫВОД

**РЕКОМЕНДАЦИЯ:** Мигрировать на НОВУЮ модель (kladr.models)

**СРОЧНОСТЬ:** КРИТИЧЕСКАЯ ❗

**ПРИЧИНА:** 2612 квартир в units используют СТАРУЮ модель → building_id=8 broken!

Нужна помощь с миграцией?
