-- SQL скрипт для создания недостающих таблиц для рефакторинга бота
-- Создаем таблицы для хранения памяти диалогов и заявок

-- Таблица для хранения состояния диалогов (memory store)
CREATE TABLE IF NOT EXISTS dialog_memory_store (
    id SERIAL PRIMARY KEY,
    dialog_id UUID NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    user_name VARCHAR(255),
    extracted_street VARCHAR(255),
    extracted_house_number VARCHAR(50),
    extracted_apartment_number VARCHAR(50),
    extracted_entrance VARCHAR(50),
    context_json JSONB,
    current_service_id INTEGER,
    current_service_name VARCHAR(255),
    previous_services JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_dialog_memory_store_dialog_id ON dialog_memory_store(dialog_id);
CREATE INDEX IF NOT EXISTS idx_dialog_memory_store_user_id ON dialog_memory_store(user_id);
CREATE INDEX IF NOT EXISTS idx_dialog_memory_store_updated_at ON dialog_memory_store(updated_at);

-- Таблица для отслеживания расходов AI
CREATE TABLE IF NOT EXISTS ai_cost_tracking (
    id SERIAL PRIMARY KEY,
    dialog_id UUID,
    user_id INTEGER NOT NULL,
    ai_provider VARCHAR(100) NOT NULL,  -- 'yandex', 'openai', 'gemini', etc.
    model_name VARCHAR(100) NOT NULL,    -- 'yandexgpt-lite', 'gpt-3.5-turbo', etc.
    service_type VARCHAR(100),           -- 'service_detection', 'address_extraction', etc.
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_rub DECIMAL(10, 6) DEFAULT 0.0,
    request_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    response_time_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    additional_data JSONB
);

-- Создаем индексы для ai_cost_tracking
CREATE INDEX IF NOT EXISTS idx_ai_cost_tracking_dialog_id ON ai_cost_tracking(dialog_id);
CREATE INDEX IF NOT EXISTS idx_ai_cost_tracking_user_id ON ai_cost_tracking(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_cost_tracking_timestamp ON ai_cost_tracking(request_timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_cost_tracking_provider ON ai_cost_tracking(ai_provider);

-- Таблица для хранения диалоговых логов (детальных логов всех сообщений)
CREATE TABLE IF NOT EXISTS dialog_logs (
    id SERIAL PRIMARY KEY,
    dialog_id UUID,
    user_id INTEGER NOT NULL,
    message_type VARCHAR(50) NOT NULL,  -- 'user_message', 'bot_response', 'system_event'
    message_content TEXT NOT NULL,
    processing_stage VARCHAR(100),      -- 'spam_filter', 'service_detection', 'address_extraction', etc.
    confidence_score DECIMAL(5, 4),
    service_detected_id INTEGER,
    address_extracted JSONB,
    processing_time_ms INTEGER,
    llm_provider VARCHAR(100),
    llm_model VARCHAR(100),
    tokens_used INTEGER,
    cost_rub DECIMAL(10, 6),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);

-- Создаем индексы для dialog_logs
CREATE INDEX IF NOT EXISTS idx_dialog_logs_dialog_id ON dialog_logs(dialog_id);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_user_id ON dialog_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_timestamp ON dialog_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_dialog_logs_message_type ON dialog_logs(message_type);

-- Таблица для хранения заявок, созданных ботом
CREATE TABLE IF NOT EXISTS bot_service_requests (
    id SERIAL PRIMARY KEY,
    request_uuid UUID DEFAULT gen_random_uuid(),
    dialog_id UUID,
    user_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    service_name VARCHAR(255),
    service_code VARCHAR(100),

    -- Адресные данные
    building_id INTEGER,
    unit_id INTEGER,
    street_name VARCHAR(255),
    house_number VARCHAR(50),
    apartment_number VARCHAR(50),
    entrance VARCHAR(50),

    -- Данные заявки
    user_name VARCHAR(255),
    user_phone VARCHAR(50),
    user_email VARCHAR(255),
    description TEXT,
    urgency_level VARCHAR(50) DEFAULT 'normal',

    -- Статусы
    status VARCHAR(50) DEFAULT 'new',  -- 'new', 'assigned', 'in_progress', 'completed', 'cancelled'
    assigned_to INTEGER,               -- ID ответственного
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Данные из AI
    confidence_score DECIMAL(5, 4),
    ai_detection_data JSONB,

    -- Дополнительная информация
    metadata JSONB
);

-- Создаем индексы для bot_service_requests
CREATE INDEX IF NOT EXISTS idx_bot_service_requests_dialog_id ON bot_service_requests(dialog_id);
CREATE INDEX IF NOT EXISTS idx_bot_service_requests_user_id ON bot_service_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_bot_service_requests_service_id ON bot_service_requests(service_id);
CREATE INDEX IF NOT EXISTS idx_bot_service_requests_status ON bot_service_requests(status);
CREATE INDEX IF NOT EXISTS idx_bot_service_requests_created_at ON bot_service_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_bot_service_requests_building_id ON bot_service_requests(building_id);

-- Добавляем внешние ключи (если таблицы services_catalog и buildings существуют)
DO $$
BEGIN
    -- Проверяем существование таблиц перед добавлением внешних ключей
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'services_catalog') THEN
        ALTER TABLE bot_service_requests
        ADD CONSTRAINT IF NOT EXISTS fk_bot_requests_service_id
        FOREIGN KEY (service_id) REFERENCES services_catalog(service_id);
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'buildings') THEN
        ALTER TABLE bot_service_requests
        ADD CONSTRAINT IF NOT EXISTS fk_bot_requests_building_id
        FOREIGN KEY (building_id) REFERENCES buildings(building_id);
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'units') THEN
        ALTER TABLE bot_service_requests
        ADD CONSTRAINT IF NOT EXISTS fk_bot_requests_unit_id
        FOREIGN KEY (unit_id) REFERENCES units(unit_id);
    END IF;
END $$;