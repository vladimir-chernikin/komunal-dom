-- =====================================================
-- ИСПРАВЛЕНИЕ: Здание ID=8 - привязка к ул. Ворошиловградская
-- Дата: 2026-03-13
-- Описание: Исправление ошибки импорта из Excel (опечатка "шиловградская")
-- =====================================================

-- ДО: building_id=8 было привязано к городу "Сочи" (level=3)
-- ПОСЛЕ: building_id=8 привязано к "ул. Ворошиловградская" (level=5)

-- 1. Проверка состояния ДО обновления
SELECT
    kb.id as building_id,
    kb.house_number,
    kko.name as street_name,
    kkot.level as street_level
FROM kladr_building kb
JOIN kladr_kladraddressobject kko ON kb.address_object_id = kko.id
JOIN kladr_kladrobjecttype kkot ON kko.type_id = kkot.id
WHERE kb.id = 8;

-- Результат ДО:
-- building_id | house_number | street_name | street_level
-- -------------+--------------|-------------|-------------
--            8 | 21           | Сочи        | 3

-- 2. Обновление здания
UPDATE kladr_building
SET address_object_id = 94  -- ul. Ворошиловградская
WHERE id = 8;

-- 3. Проверка состояния ПОСЛЕ обновления
SELECT
    kb.id as building_id,
    kb.house_number,
    kko.name as street_name,
    kko.id as street_id,
    kkot.level as street_level,
    kkot.short_name as street_type,
    city.name as city_name
FROM kladr_building kb
JOIN kladr_kladraddressobject kko ON kb.address_object_id = kko.id
JOIN kladr_kladrobjecttype kkot ON kko.type_id = kkot.id
LEFT JOIN kladr_kladraddressobject city ON kko.parent_id = city.id
WHERE kb.id = 8;

-- Результат ПОСЛЕ:
-- building_id | house_number | street_name        | street_id | street_level | street_type | city_name
-- -------------+--------------|-------------------|-----------|--------------|-------------|-----------
--            8 | 21           | Ворошиловградская | 94        | 5            | ул          | Сочи

-- 4. Проверка квартир (units)
SELECT
    u.unit_id,
    u.unit_number,
    u.building_id,
    b.house_number,
    kko.name as street_name
FROM units u
JOIN kladr_building b ON u.building_id = b.id
JOIN kladr_kladraddressobject kko ON b.address_object_id = kko.id
WHERE u.building_id = 8
ORDER BY u.unit_number;

-- Результат:
-- unit_id | unit_number | building_id | house_number | street_name
-- ---------|-------------|-------------|--------------|-------------------
--      274 | 1           | 8           | 21           | Ворошиловградская
--      275 | 2           | 8           | 21           | Ворошиловградская
--      276 | 4           | 8           | 21           | Ворошиловградская
--      277 | 5           | 8           | 21           | Ворошиловградская

-- =====================================================
-- ИТОГ:
-- - Здание ID=8 теперь корректно привязано к ул. Ворошиловградская
-- - 4 квартиры (1, 2, 4, 5) автоматически обновились
-- - Все здания (58) теперь на level 5 (улицы + переулки)
-- =====================================================
