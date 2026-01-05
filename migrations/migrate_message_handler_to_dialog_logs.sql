-- Миграция: Перенос данных из message_handler_messagelog в dialog_logs
-- Дата: 2026-01-05
-- Описание: Объединение двух систем логирования в одну таблицу

BEGIN;

-- Шаг 1: Перенос данных из message_handler_messagelog в dialog_logs
INSERT INTO dialog_logs (
    dialog_id,
    user_id,
    message_type,
    message_content,
    channel,
    direction,
    message_id,
    session_id,
    django_user_id,
    metadata,
    timestamp
)
SELECT
    -- Генерируем UUID для dialog_id на основе session_id
    CASE
        WHEN session_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
            session_id::uuid
        ELSE
            md5(session_id || created_at::text)::uuid
    END as dialog_id,
    -- Конвертируем user_id из varchar в integer
    CASE
        WHEN user_id ~ '^[0-9]+$' THEN user_id::integer
        ELSE 0
    END as user_id,
    -- direction -> message_type
    direction as message_type,
    text as message_content,
    channel,
    direction,
    message_id,
    session_id,
    django_user_id,
    metadata,
    created_at as timestamp
FROM message_handler_messagelog
ON CONFLICT DO NOTHING;  -- Если запись уже есть, пропускаем

-- Шаг 2: Проверка количества перенесенных записей
DO $$
DECLARE
    old_count integer;
    new_count integer;
BEGIN
    SELECT COUNT(*) INTO old_count FROM message_handler_messagelog;
    SELECT COUNT(*) INTO new_count FROM dialog_logs;

    RAISE NOTICE 'Перенесено записей: % из %', new_count, old_count;
END $$;

-- Шаг 3: Создаем бэкап таблицы перед удалением
-- CREATE TABLE message_handler_messagelog_backup AS SELECT * FROM message_handler_messagelog;

-- Шаг 4: Удаляем старую таблицу
-- DROP TABLE IF EXISTS message_handler_messagelog CASCADE;

COMMIT;

-- ВНИМАНИЕ: Шаг 4 (DROP TABLE) закомментирован для безопасности!
-- Раскомментируйте после проверки что данные успешно перенесены.
