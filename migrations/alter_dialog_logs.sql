-- Миграция: Дополнение таблицы dialog_logs полями из message_handler_messagelog
-- Дата: 2026-01-03
-- Описание: Добавляем недостающие поля для замены message_handler_messagelog

-- 1. Добавляем недостающие поля
ALTER TABLE dialog_logs ADD COLUMN IF NOT EXISTS channel VARCHAR(50);
ALTER TABLE dialog_logs ADD COLUMN IF NOT EXISTS direction VARCHAR(20);  -- inbound, outbound, system
ALTER TABLE dialog_logs ADD COLUMN IF NOT EXISTS message_id VARCHAR(100);
ALTER TABLE dialog_logs ADD COLUMN IF NOT EXISTS session_id VARCHAR(100);
ALTER TABLE dialog_logs ADD COLUMN IF NOT EXISTS django_user_id INTEGER;

-- 2. Добавляем комментарии
COMMENT ON COLUMN dialog_logs.channel IS 'Канал связи: telegram, web, whatsapp, test_bot';
COMMENT ON COLUMN dialog_logs.direction IS 'Направление: inbound (от пользователя), outbound (от бота), system (служебное)';
COMMENT ON COLUMN dialog_logs.message_id IS 'ID сообщения в канале';
COMMENT ON COLUMN dialog_logs.session_id IS 'ID сессии диалога';
COMMENT ON COLUMN dialog_logs.django_user_id IS 'ID пользователя Django (если есть)';

-- 3. Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_dialog_logs_channel ON dialog_logs(channel);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_direction ON dialog_logs(direction);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_session_id ON dialog_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_dialog_id ON dialog_logs(dialog_id);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_timestamp ON dialog_logs(timestamp DESC);

-- 4. Уникальный индекс для message_id (чтобы избежать дублей)
CREATE UNIQUE INDEX IF NOT EXISTS idx_dialog_logs_message_id_unique ON dialog_logs(message_id) WHERE message_id IS NOT NULL;
