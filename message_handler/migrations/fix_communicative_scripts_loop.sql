-- Миграция: Исправление зацикливания коммуникативных скриптов
-- Дата: 2026-01-21
-- Проблема: max_dialog_turn=-1 создавало бесконечный цикл fallback сообщений
-- Решение: Ограничение количества повторений + финальный fallback для передачи оператору

-- Обновляем fallback скрипты: ограничиваем количество повторений до 5
UPDATE message_handler_communicativescript
SET max_dialog_turn = 5
WHERE script_name IN (
    'fallback_followup_clarify',
    'fallback_clarify_location',
    'fallback_clarify_object',
    'fallback_clarify_details'
);

-- Обновляем clarification скрипты: ограничиваем количество повторений до 5
UPDATE message_handler_communicativescript
SET max_dialog_turn = 5
WHERE script_type = 'clarification' AND max_dialog_turn = -1;

-- Создаем финальный fallback скрипт для передачи оператору (после 6 попыток)
INSERT INTO message_handler_communicativescript (
    script_name, script_type, channel, text, conditions,
    priority, max_uses_per_day, min_dialog_turn, max_dialog_turn,
    is_active, category, notes, created_at, updated_at
) VALUES (
    'fallback_final_operator',
    'fallback',
    'telegram',
    'К сожалению, я не смог определить вашу проблему. Пожалуйста, свяжитесь с оператором по телефону.',
    '{"is_followup": true, "candidate_count": 0}'::jsonb,
    1.0,
    -1,
    6,
    -1,
    true,
    'final',
    'Финальный fallback после 5 попыток - передача оператору',
    NOW(),
    NOW()
) ON CONFLICT (script_name) DO UPDATE SET
    max_dialog_turn = 6,
    max_uses_per_day = -1,
    text = 'К сожалению, я не смог определить вашу проблему. Пожалуйста, свяжитесь с оператором по телефону.',
    updated_at = NOW();

-- Результат:
-- Ходы 1-3: fallback_no_candidates
-- Ходы 2-5: fallback_followup_clarify, fallback_clarify_location, fallback_clarify_object, fallback_clarify_details
-- Ход 6+: fallback_final_operator (передача оператору)
-- clarification скрипты: ограничены 5ю ходами
