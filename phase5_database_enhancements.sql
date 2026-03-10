-- ЧАСТЬ 5: Расширенное логирование и аналитика для рефакторинга бота
-- Создание views, функций и триггеров для аналитики

-- =====================================================
-- 5.1 Добавление полей в существующие таблицы
-- =====================================================

-- Добавляем поля в debug_trace_log для расширенного логирования
ALTER TABLE debug_trace_log
ADD COLUMN IF NOT EXISTS user_name VARCHAR(100),
ADD COLUMN IF NOT EXISTS dialog_context JSONB,
ADD COLUMN IF NOT EXISTS ai_model_used VARCHAR(50),
ADD COLUMN IF NOT EXISTS ai_tokens_used INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS ai_cost_usd NUMERIC(10, 8) DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS ai_cost_rub NUMERIC(10, 6) DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS extracted_address JSONB,
ADD COLUMN IF NOT EXISTS service_confidence NUMERIC(3, 2) DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS duration_total_ms INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS final_ticket_id UUID;

-- Добавляем поля в dialog_memory_store для улучшенной функциональности
ALTER TABLE dialog_memory_store
ADD COLUMN IF NOT EXISTS dialog_status VARCHAR(50) DEFAULT 'active',
ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS ai_requests_count INTEGER DEFAULT 0;

-- Добавляем индексы для новых полей
CREATE INDEX IF NOT EXISTS idx_debug_trace_log_user_name ON debug_trace_log(user_name);
CREATE INDEX IF NOT EXISTS idx_debug_trace_log_ai_model ON debug_trace_log(ai_model_used);
CREATE INDEX IF NOT EXISTS idx_debug_trace_log_confidence ON debug_trace_log(service_confidence);
CREATE INDEX IF NOT EXISTS idx_dialog_memory_store_status ON dialog_memory_store(dialog_status);
CREATE INDEX IF NOT EXISTS idx_dialog_memory_store_activity ON dialog_memory_store(last_activity_at);

-- =====================================================
-- 5.2 Создание Views для аналитики
-- =====================================================

-- View 1: v_daily_ai_costs - дневная статистика расходов AI
CREATE OR REPLACE VIEW v_daily_ai_costs AS
SELECT
    DATE(request_timestamp) as date,
    model_name,
    ai_provider,
    COUNT(*) as requests_count,
    SUM(total_tokens) as total_tokens,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cost_rub) as total_cost_rub,
    AVG(response_time_ms) as avg_response_time_ms,
    MIN(response_time_ms) as min_response_time_ms,
    MAX(response_time_ms) as max_response_time_ms,
    SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests,
    ROUND(
        (SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*)), 2
    ) as success_rate_percent
FROM ai_cost_tracking
GROUP BY DATE(request_timestamp), model_name, ai_provider
ORDER BY date DESC, total_cost_rub DESC;

-- View 2: v_monthly_ai_costs - месячная статистика расходов AI
CREATE OR REPLACE VIEW v_monthly_ai_costs AS
SELECT
    DATE_TRUNC('month', request_timestamp)::date as month,
    model_name,
    ai_provider,
    COUNT(*) as requests_count,
    SUM(total_tokens) as total_tokens,
    SUM(cost_rub) as total_cost_rub,
    AVG(response_time_ms) as avg_response_time_ms,
    SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests,
    ROUND(
        (SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(*)), 2
    ) as success_rate_percent
FROM ai_cost_tracking
GROUP BY DATE_TRUNC('month', request_timestamp), model_name, ai_provider
ORDER BY month DESC, total_cost_rub DESC;

-- View 3: v_dialog_stats - статистика по диалогам
CREATE OR REPLACE VIEW v_dialog_stats AS
SELECT
    dml.dialog_id,
    dml.user_id,
    dml.user_name,
    dml.current_service_name,
    dml.dialog_status,
    dml.created_at,
    dml.updated_at,
    dml.last_activity_at,
    dml.message_count,
    dml.ai_requests_count,
    (dml.updated_at - dml.created_at) as dialog_duration_minutes,
    COUNT(DISTINCT aih.id) as ai_requests_from_tracking,
    COALESCE(SUM(aih.cost_rub), 0) as total_ai_cost_rub,
    COALESCE(SUM(aih.total_tokens), 0) as total_tokens_used,
    -- Средняя успешность AI запросов
    CASE
        WHEN COUNT(aih.id) > 0 THEN
            ROUND(
                (SUM(CASE WHEN aih.success = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(aih.id)), 2
            )
        ELSE 0
    END as ai_success_rate_percent
FROM dialog_memory_store dml
LEFT JOIN ai_cost_tracking aih ON aih.dialog_id::text = dml.dialog_id::text
GROUP BY dml.dialog_id, dml.user_id, dml.user_name, dml.current_service_name,
         dml.dialog_status, dml.created_at, dml.updated_at, dml.last_activity_at,
         dml.message_count, dml.ai_requests_count
ORDER BY dml.updated_at DESC;

-- View 4: v_service_performance - производительность услуг
CREATE OR REPLACE VIEW v_service_performance AS
SELECT
    sc.service_id,
    sc.scenario_name,
    rc.category_name,
    COUNT(*) as total_requests,
    AVG(CAST(dtcl.service_confidence AS NUMERIC)) as avg_confidence,
    COUNT(DISTINCT dtcl.user_id) as unique_users,
    COUNT(DISTINCT DATE(dtcl.created_at)) as active_days,
    MIN(dtcl.created_at) as first_request,
    MAX(dtcl.created_at) as last_request,
    -- Статистика по стоимости
    COALESCE(SUM(dtcl.ai_cost_rub), 0) as total_cost_rub,
    COALESCE(AVG(dtcl.ai_cost_rub), 0) as avg_cost_rub
FROM debug_trace_log dtcl
LEFT JOIN services_catalog sc ON dtcl.service_id = sc.service_id
LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
WHERE dtcl.final_status = 'SUCCESS'
  AND dtcl.service_id IS NOT NULL
GROUP BY sc.service_id, sc.scenario_name, rc.category_name
ORDER BY total_requests DESC;

-- View 5: v_user_activity - активность пользователей
CREATE OR REPLACE VIEW v_user_activity AS
SELECT
    dml.user_id,
    dml.user_name,
    COUNT(*) as total_dialogs,
    SUM(dml.message_count) as total_messages,
    SUM(dml.ai_requests_count) as total_ai_requests,
    COALESCE(SUM(aih.cost_rub), 0) as total_cost_rub,
    COALESCE(SUM(aih.total_tokens), 0) as total_tokens,
    COUNT(DISTINCT DATE(dml.created_at)) as active_days,
    MIN(dml.created_at) as first_dialog,
    MAX(dml.last_activity_at) as last_activity,
    -- Средняя стоимость对话
    CASE
        WHEN COUNT(*) > 0 THEN COALESCE(SUM(aih.cost_rub), 0) / COUNT(*)
        ELSE 0
    END as avg_cost_per_dialog
FROM dialog_memory_store dml
LEFT JOIN ai_cost_tracking aih ON aih.dialog_id::text = dml.dialog_id::text
GROUP BY dml.user_id, dml.user_name
ORDER BY total_dialogs DESC;

-- =====================================================
-- 5.3 Создание функций для расчета
-- =====================================================

-- Функция 1: fn_get_daily_budget_info()
CREATE OR REPLACE FUNCTION fn_get_daily_budget_info(target_date date DEFAULT CURRENT_DATE)
RETURNS TABLE (
    date date,
    total_requests bigint,
    total_tokens bigint,
    total_cost_usd numeric,
    total_cost_rub numeric,
    success_rate numeric,
    avg_response_time numeric,
    by_model json
) AS $$
BEGIN
    RETURN QUERY
    WITH daily_summary AS (
        SELECT
            COUNT(*) as req_count,
            SUM(total_tokens) as token_sum,
            SUM(cost_rub) as cost_sum,
            AVG(response_time_ms) as avg_time,
            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as success_count
        FROM ai_cost_tracking
        WHERE DATE(request_timestamp) = target_date
    ),
    model_summary AS (
        SELECT
            model_name,
            COUNT(*) as requests,
            SUM(total_tokens) as tokens,
            SUM(cost_rub) as cost,
            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful
        FROM ai_cost_tracking
        WHERE DATE(request_timestamp) = target_date
        GROUP BY model_name
    )
    SELECT
        target_date,
        ds.req_count::bigint,
        ds.token_sum::bigint,
        (ds.cost_sum / 100.0)::numeric as cost_usd,
        ds.cost_sum::numeric as cost_rub,
        CASE
            WHEN ds.req_count > 0 THEN (ds.success_count * 100.0 / ds.req_count)
            ELSE 0
        END as success_rate,
        ds.avg_time::numeric,
        json_object_agg(
            model_name,
            json_build_object(
                'requests', requests,
                'tokens', tokens,
                'cost_rub', cost,
                'success_rate', CASE
                    WHEN requests > 0 THEN (successful * 100.0 / requests)
                    ELSE 0
                END
            )
        )::json as by_model
    FROM daily_summary ds, model_summary ms;

    -- Если нет данных за день, возвращаем пустые значения
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            target_date, 0::bigint, 0::bigint, 0.0::numeric, 0.0::numeric,
            0.0::numeric, 0.0::numeric, '{}'::json;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Функция 2: fn_get_monthly_budget_info()
CREATE OR REPLACE FUNCTION fn_get_monthly_budget_info(target_year integer DEFAULT EXTRACT(YEAR FROM CURRENT_DATE),
                                                     target_month integer DEFAULT EXTRACT(MONTH FROM CURRENT_DATE))
RETURNS TABLE (
    year integer,
    month integer,
    total_requests bigint,
    total_tokens bigint,
    total_cost_usd numeric,
    total_cost_rub numeric,
    success_rate numeric,
    avg_response_time numeric,
    daily_breakdown json
) AS $$
BEGIN
    RETURN QUERY
    WITH daily_data AS (
        SELECT
            DATE(request_timestamp) as date,
            COUNT(*)::bigint as requests,
            SUM(total_tokens)::bigint as tokens,
            SUM(cost_rub)::numeric as cost,
            AVG(response_time_ms)::numeric as avg_time,
            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END)::bigint as successful
        FROM ai_cost_tracking
        WHERE EXTRACT(YEAR FROM request_timestamp) = target_year
          AND EXTRACT(MONTH FROM request_timestamp) = target_month
        GROUP BY DATE(request_timestamp)
    ),
    month_summary AS (
        SELECT
            SUM(requests) as total_requests,
            SUM(tokens) as total_tokens,
            SUM(cost) as total_cost,
            AVG(avg_time) as avg_time,
            SUM(successful) as total_successful
        FROM daily_data
    )
    SELECT
        target_year,
        target_month,
        ms.total_requests,
        ms.total_tokens,
        (ms.total_cost / 100.0)::numeric as total_cost_usd,
        ms.total_cost::numeric as total_cost_rub,
        CASE
            WHEN ms.total_requests > 0 THEN (ms.total_successful * 100.0 / ms.total_requests)
            ELSE 0
        END::numeric as success_rate,
        ms.avg_time::numeric as avg_response_time,
        json_agg(
            json_build_object(
                'date', date::text,
                'requests', requests,
                'tokens', tokens,
                'cost_rub', cost,
                'success_rate', CASE
                    WHEN requests > 0 THEN (successful * 100.0 / requests)
                    ELSE 0
                END
            ) ORDER BY date
        )::json as daily_breakdown
    FROM month_summary ms, daily_data dd
    GROUP BY target_year, target_month, ms.total_requests, ms.total_tokens, ms.total_cost,
             ms.avg_time, ms.total_successful;
END;
$$ LANGUAGE plpgsql;

-- Функция 3: fn_calculate_ai_cost()
CREATE OR REPLACE FUNCTION fn_calculate_ai_cost(model_name varchar, tokens integer)
RETURNS numeric AS $$
DECLARE
    rate numeric;
BEGIN
    rate := CASE
        WHEN model_name = 'yandexgpt-lite' THEN 0.00024
        WHEN model_name = 'yandexgpt-pro' THEN 0.0005
        WHEN model_name = 'yandexgpt-plus' THEN 0.0007
        WHEN model_name = 'gpt-3.5-turbo' THEN 0.0005
        WHEN model_name = 'gpt-4' THEN 0.003
        WHEN model_name = 'gpt-4-turbo' THEN 0.001
        WHEN model_name = 'gemini-pro' THEN 0.00005
        WHEN model_name = 'claude-3-sonnet' THEN 0.00075
        WHEN model_name = 'claude-3-opus' THEN 0.0025
        ELSE 0.0
    END;

    RETURN (tokens::numeric / 1000) * rate;
END;
$$ LANGUAGE plpgsql;

-- Функция 4: fn_get_user_activity_summary()
CREATE OR REPLACE FUNCTION fn_get_user_activity_summary(user_id_param integer)
RETURNS TABLE (
    user_id integer,
    user_name varchar,
    total_dialogs bigint,
    total_messages bigint,
    total_ai_requests bigint,
    total_cost_rub numeric,
    avg_cost_per_dialog numeric,
    success_rate numeric,
    last_activity timestamptz
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        dml.user_id,
        dml.user_name,
        COUNT(*)::bigint as total_dialogs,
        SUM(dml.message_count)::bigint as total_messages,
        COALESCE(SUM(aih.total_tokens), 0)::bigint as total_ai_requests,
        COALESCE(SUM(aih.cost_rub), 0)::numeric as total_cost_rub,
        CASE
            WHEN COUNT(*) > 0 THEN COALESCE(SUM(aih.cost_rub), 0) / COUNT(*)
            ELSE 0
        END::numeric as avg_cost_per_dialog,
        CASE
            WHEN COUNT(aih.id) > 0 THEN
                (SUM(CASE WHEN aih.success = TRUE THEN 1 ELSE 0 END) * 100.0 / COUNT(aih.id))
            ELSE 0
        END::numeric as success_rate,
        MAX(dml.last_activity_at) as last_activity
    FROM dialog_memory_store dml
    LEFT JOIN ai_cost_tracking aih ON aih.dialog_id::text = dml.dialog_id::text
    WHERE dml.user_id = user_id_param
    GROUP BY dml.user_id, dml.user_name;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 5.4 Создание триггеров
-- =====================================================

-- Триггер 1: trg_update_dialog_memory_timestamp
CREATE OR REPLACE FUNCTION fn_update_dialog_memory_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.last_activity_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_dialog_memory_timestamp ON dialog_memory_store;
CREATE TRIGGER trg_update_dialog_memory_timestamp
BEFORE UPDATE ON dialog_memory_store
FOR EACH ROW
EXECUTE FUNCTION fn_update_dialog_memory_timestamp();

-- Триггер 2: trg_calculate_ai_cost_on_insert
CREATE OR REPLACE FUNCTION fn_calculate_ai_cost_on_insert()
RETURNS TRIGGER AS $$
BEGIN
    -- Рассчитываем стоимость если она не установлена
    IF NEW.cost_rub IS NULL OR NEW.cost_rub = 0 THEN
        NEW.cost_rub = COALESCE(
            (fn_calculate_ai_cost(NEW.model_name, NEW.total_tokens) * 100), 0
        );
    END IF;

    -- Рассчитываем total_tokens если не установлено
    IF NEW.total_tokens IS NULL OR NEW.total_tokens = 0 THEN
        NEW.total_tokens = COALESCE(NEW.input_tokens, 0) + COALESCE(NEW.output_tokens, 0);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_calculate_ai_cost ON ai_cost_tracking;
CREATE TRIGGER trg_calculate_ai_cost
BEFORE INSERT ON ai_cost_tracking
FOR EACH ROW
EXECUTE FUNCTION fn_calculate_ai_cost_on_insert();

-- Триггер 3: trg_update_dialog_counters
CREATE OR REPLACE FUNCTION fn_update_dialog_counters()
RETURNS TRIGGER AS $$
BEGIN
    -- Увеличиваем счетчик AI запросов в dialog_memory_store
    UPDATE dialog_memory_store
    SET ai_requests_count = COALESCE(ai_requests_count, 0) + 1,
        last_activity_at = NOW()
    WHERE dialog_id = NEW.dialog_id::uuid;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_dialog_counters ON ai_cost_tracking;
CREATE TRIGGER trg_update_dialog_counters
AFTER INSERT ON ai_cost_tracking
FOR EACH ROW
EXECUTE FUNCTION fn_update_dialog_counters();

-- =====================================================
-- 5.5 Хранимые процедуры для обслуживания
-- =====================================================

-- Процедура 1: proc_cleanup_old_dialogs
CREATE OR REPLACE PROCEDURE proc_cleanup_old_dialogs(days_old integer DEFAULT 30)
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count integer;
BEGIN
    -- Удаляем старые диалоги из dialog_memory_store
    DELETE FROM dialog_memory_store
    WHERE updated_at < NOW() - (days_old || ' days')::interval;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Cleaned up % old dialog memory records older than % days', deleted_count, days_old;

    -- Удаляем старые записи из debug_trace_log
    DELETE FROM debug_trace_log
    WHERE created_at < NOW() - (days_old || ' days')::interval;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Cleaned up % old trace log records older than % days', deleted_count, days_old;
END;
$$;

-- Процедура 2: proc_analyze_dialog_performance
CREATE OR REPLACE PROCEDURE proc_analyze_dialog_performance()
LANGUAGE plpgsql
AS $$
BEGIN
    -- Создаем временную таблицу для анализа
    DROP TABLE IF EXISTS temp_dialog_analysis;
    CREATE TEMP TABLE temp_dialog_analysis AS
    SELECT
        dml.dialog_id,
        dml.user_id,
        dml.user_name,
        dml.current_service_name,
        EXTRACT(EPOCH FROM (dml.updated_at - dml.created_at))/60 as duration_minutes,
        dml.message_count,
        COALESCE(dml.ai_requests_count, 0) as ai_requests,
        COALESCE(ai_stats.total_cost, 0) as ai_cost,
        COALESCE(ai_stats.total_tokens, 0) as tokens_used
    FROM dialog_memory_store dml
    LEFT JOIN (
        SELECT
            dialog_id,
            SUM(cost_rub) as total_cost,
            SUM(total_tokens) as total_tokens
        FROM ai_cost_tracking
        GROUP BY dialog_id
    ) ai_stats ON dml.dialog_id::text = ai_stats.dialog_id
    WHERE dml.created_at >= CURRENT_DATE - INTERVAL '7 days';

    -- Выводим статистику
    RAISE NOTICE 'Dialog Performance Analysis (last 7 days):';

    -- Средняя длительность диалога
    RAISE NOTICE 'Average dialog duration: % minutes',
        (SELECT AVG(duration_minutes) FROM temp_dialog_analysis);

    -- Среднее количество сообщений
    RAISE NOTICE 'Average messages per dialog: %',
        (SELECT AVG(message_count) FROM temp_dialog_analysis);

    -- Средняя стоимость AI
    RAISE NOTICE 'Average AI cost per dialog: %₽',
        (SELECT AVG(ai_cost) FROM temp_dialog_analysis);

    -- Топ-5 самых активных пользователей
    RAISE NOTICE 'Top 5 most active users:';
    FOR user_rec IN
        SELECT user_name, COUNT(*) as dialogs, SUM(ai_cost) as total_cost
        FROM temp_dialog_analysis
        WHERE user_name IS NOT NULL
        GROUP BY user_name
        ORDER BY dialogs DESC
        LIMIT 5
    LOOP
        RAISE NOTICE '  %: % dialogs, %₽ total', user_rec.user_name, user_rec.dialogs, user_rec.total_cost;
    END LOOP;
END;
$$;

-- =====================================================
-- 5.6 Создание отчетных функций
-- =====================================================

-- Функция: fn_generate_daily_report()
CREATE OR REPLACE FUNCTION fn_generate_daily_report(target_date date DEFAULT CURRENT_DATE)
RETURNS TABLE (
    report_date date,
    total_dialogs bigint,
    successful_requests bigint,
    total_cost_rub numeric,
    avg_response_time numeric,
    top_services json
) AS $$
BEGIN
    RETURN QUERY
    WITH daily_summary AS (
        SELECT
            COUNT(DISTINCT dml.dialog_id) as total_dialogs,
            COUNT(DISTINCT dtcl.trace_id) as total_requests,
            SUM(CASE WHEN dtcl.final_status = 'SUCCESS' THEN 1 ELSE 0 END) as successful_requests,
            COALESCE(SUM(aih.cost_rub), 0) as total_cost,
            COALESCE(AVG(aih.response_time_ms), 0) as avg_response_time
        FROM dialog_memory_store dml
        LEFT JOIN debug_trace_log dtcl ON dml.dialog_id = dtcl.dialog_id
        LEFT JOIN ai_cost_tracking aih ON dml.dialog_id::text = aih.dialog_id
        WHERE DATE(dml.created_at) = target_date
           OR DATE(dtcl.created_at) = target_date
    ),
    top_services AS (
        SELECT
            json_agg(
                json_build_object(
                    'service_name', service_name,
                    'requests', service_count,
                    'success_rate', success_rate
                ) ORDER BY service_count DESC
            ) as services
        FROM (
            SELECT
                dtcl.final_service_name as service_name,
                COUNT(*) as service_count,
                ROUND(
                    (SUM(CASE WHEN dtcl.final_status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)), 2
                ) as success_rate
            FROM debug_trace_log dtcl
            WHERE DATE(dtcl.created_at) = target_date
              AND dtcl.final_service_name IS NOT NULL
            GROUP BY dtcl.final_service_name
            ORDER BY service_count DESC
            LIMIT 5
        ) top_svc
    )
    SELECT
        target_date,
        COALESCE(ds.total_dialogs, 0)::bigint,
        COALESCE(ds.successful_requests, 0)::bigint,
        COALESCE(ds.total_cost, 0)::numeric,
        ds.avg_response_time::numeric,
        COALESCE(ts.services, '{}'::json) as top_services
    FROM daily_summary ds, top_services ts;
END;
$$ LANGUAGE plpgsql;

-- Комментируем для информирования
COMMENT ON FUNCTION fn_get_daily_budget_info(date) IS 'Возвращает подробную статистику расходов AI за день';
COMMENT ON FUNCTION fn_get_monthly_budget_info(integer, integer) IS 'Возвращает месячную статистику расходов AI с разбивкой по дням';
COMMENT ON FUNCTION fn_calculate_ai_cost(varchar, integer) IS 'Рассчитывает стоимость AI запроса на основе модели и количества токенов';
COMMENT ON FUNCTION fn_get_user_activity_summary(integer) IS 'Возвращает сводную статистику активности пользователя';
COMMENT ON PROCEDURE proc_cleanup_old_dialogs(integer) IS 'Очищает старые записи диалогов и логов';
COMMENT ON PROCEDURE proc_analyze_dialog_performance() IS 'Анализирует производительность диалогов за последние 7 дней';
COMMENT ON FUNCTION fn_generate_daily_report(date) IS 'Генерирует ежедневный отчет по активности системы';

-- =====================================================
-- Завершение выполнения скрипта
-- =====================================================

-- Информационное сообщение
DO $$
BEGIN
    RAISE NOTICE '=== ЧАСТЬ 5: Расширенное логирование и аналитика успешно установлена ===';
    RAISE NOTICE 'Созданы:';
    RAISE NOTICE '- 5 Views для аналитики (v_daily_ai_costs, v_monthly_ai_costs, v_dialog_stats, v_service_performance, v_user_activity)';
    RAISE NOTICE '- 4 функции расчета (fn_get_daily_budget_info, fn_get_monthly_budget_info, fn_calculate_ai_cost, fn_get_user_activity_summary)';
    RAISE NOTICE '- 3 триггера автоматизации (trg_update_dialog_memory_timestamp, trg_calculate_ai_cost, trg_update_dialog_counters)';
    RAISE NOTICE '- 2 процедуры обслуживания (proc_cleanup_old_dialogs, proc_analyze_dialog_performance)';
    RAISE NOTICE '- 1 отчетная функция (fn_generate_daily_report)';
    RAISE NOTICE '';
    RAISE NOTICE 'Для просмотра ежедневной статистики:';
    RAISE NOTICE 'SELECT * FROM fn_get_daily_budget_info();';
    RAISE NOTICE '';
    RAISE NOTICE 'Для просмотра месячной статистики:';
    RAISE NOTICE 'SELECT * FROM fn_get_monthly_budget_info(2025, 12);';
    RAISE NOTICE '';
    RAISE NOTICE 'Для анализа производительности:';
    RAISE NOTICE 'CALL proc_analyze_dialog_performance();';
END $$;