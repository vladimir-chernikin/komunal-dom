-- Миграция: Создание таблицы llm_request_log
-- Дата: 2026-01-03
-- Описание: Таблица для логирования всех запросов к LLM

CREATE TABLE IF NOT EXISTS llm_request_log (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL DEFAULT gen_random_uuid(),
    provider VARCHAR(50) NOT NULL,  -- yandexgpt, gigachat, openai, openrouter
    model VARCHAR(100) NOT NULL,    -- yandexgpt-lite, gpt-4, etc
    prompt_text TEXT NOT NULL,
    response_text TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    cost_rub NUMERIC(10, 4),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    error_message TEXT,
    status VARCHAR(20) DEFAULT 'success'  -- success, error, timeout
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_llm_request_log_provider ON llm_request_log(provider);
CREATE INDEX IF NOT EXISTS idx_llm_request_log_created ON llm_request_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_request_log_request_id ON llm_request_log(request_id);

-- Комментарии
COMMENT ON TABLE llm_request_log IS 'Лог всех запросов к LLM (YandexGPT, GigaChat, OpenAI, etc)';
COMMENT ON COLUMN llm_request_log.provider IS 'Провайдер LLM: yandexgpt, gigachat, openai, openrouter';
COMMENT ON COLUMN llm_request_log.model IS 'Модель LLM: yandexgpt-lite, gpt-4, etc';
COMMENT ON COLUMN llm_request_log.cost_rub IS 'Стоимость запроса в рублях';
