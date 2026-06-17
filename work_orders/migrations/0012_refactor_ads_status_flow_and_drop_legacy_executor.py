from django.db import migrations


STATUS_FLOW_SQL = """
UPDATE request_mgmt.work_order_status_ref
SET short_name_ru = 'Назначен ответственный',
    display_name_for_user = 'Назначен ответственный',
    description_and_transition_rules = 'Ответственный исполнитель установлен. Следующий штатный шаг - перевод в статус "В работе".',
    sort_order = 200,
    is_terminal = FALSE,
    is_active = TRUE
WHERE short_code_en = 'accepted_by_executor';

INSERT INTO request_mgmt.work_order_status_ref
    (short_code_en, short_name_ru, display_name_for_user, description_and_transition_rules, sort_order, is_terminal, is_active, created_at, updated_at, is_test)
VALUES
    ('localized', 'Локализовано', 'Локализовано', 'Проблема локализована. Следующий штатный шаг - перевод в статус "Выполнена".', 400, FALSE, TRUE, NOW(), NOW(), FALSE)
ON CONFLICT (short_code_en) DO UPDATE
SET short_name_ru = EXCLUDED.short_name_ru,
    display_name_for_user = EXCLUDED.display_name_for_user,
    description_and_transition_rules = EXCLUDED.description_and_transition_rules,
    sort_order = EXCLUDED.sort_order,
    is_terminal = EXCLUDED.is_terminal,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

UPDATE request_mgmt.work_order_status_ref
SET sort_order = 500,
    is_terminal = FALSE,
    is_active = TRUE,
    description_and_transition_rules = 'Работы завершены. Закрыть заявку могут главный инженер, директор УК или Django-суперпользователь.'
WHERE short_code_en = 'completed';

UPDATE request_mgmt.work_order_status_ref
SET sort_order = 600,
    is_terminal = TRUE,
    is_active = TRUE
WHERE short_code_en = 'closed';

UPDATE request_mgmt.work_order_status_ref
SET sort_order = 800
WHERE short_code_en = 'cancelled';

UPDATE request_mgmt.work_order_status_ref
SET sort_order = 850
WHERE short_code_en = 'on_hold';

UPDATE request_mgmt.work_order_status_ref
SET sort_order = 900
WHERE short_code_en = 'reopened';

DELETE FROM request_mgmt.work_order_status_transition;

INSERT INTO request_mgmt.work_order_status_transition
    (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment, require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned, is_active, created_at, updated_at, is_test)
SELECT fs.id, ts.id, NULL, FALSE, FALSE, FALSE, FALSE, FALSE, TRUE, TRUE, NOW(), NOW(), FALSE
FROM request_mgmt.work_order_status_ref fs
JOIN request_mgmt.work_order_status_ref ts ON ts.short_code_en = 'accepted_by_executor'
WHERE fs.short_code_en = 'new_registered';

INSERT INTO request_mgmt.work_order_status_transition
    (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment, require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned, is_active, created_at, updated_at, is_test)
SELECT fs.id, ts.id, roles.role_code, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, TRUE, NOW(), NOW(), FALSE
FROM request_mgmt.work_order_status_ref fs
JOIN request_mgmt.work_order_status_ref ts ON ts.short_code_en = 'in_progress'
CROSS JOIN (VALUES ('executor'), ('contractor')) AS roles(role_code)
WHERE fs.short_code_en = 'accepted_by_executor';

INSERT INTO request_mgmt.work_order_status_transition
    (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment, require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned, is_active, created_at, updated_at, is_test)
SELECT fs.id, ts.id, roles.role_code, FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, TRUE, NOW(), NOW(), FALSE
FROM request_mgmt.work_order_status_ref fs
JOIN request_mgmt.work_order_status_ref ts ON ts.short_code_en = 'localized'
CROSS JOIN (VALUES ('executor'), ('contractor')) AS roles(role_code)
WHERE fs.short_code_en = 'in_progress';

INSERT INTO request_mgmt.work_order_status_transition
    (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment, require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned, is_active, created_at, updated_at, is_test)
SELECT fs.id, ts.id, roles.role_code, FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, TRUE, NOW(), NOW(), FALSE
FROM request_mgmt.work_order_status_ref fs
JOIN request_mgmt.work_order_status_ref ts ON ts.short_code_en = 'completed'
CROSS JOIN (VALUES ('executor'), ('contractor')) AS roles(role_code)
WHERE fs.short_code_en = 'localized';

INSERT INTO request_mgmt.work_order_status_transition
    (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment, require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned, is_active, created_at, updated_at, is_test)
SELECT fs.id, ts.id, roles.role_code, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, TRUE, NOW(), NOW(), FALSE
FROM request_mgmt.work_order_status_ref fs
JOIN request_mgmt.work_order_status_ref ts ON ts.short_code_en = 'closed'
CROSS JOIN (VALUES ('chief_engineer'), ('direktor_uk'), ('django_admin')) AS roles(role_code)
WHERE fs.short_code_en = 'completed';

DROP TABLE IF EXISTS public.bot_service_requests CASCADE;
DROP TABLE IF EXISTS public.bot_service_requests_backup CASCADE;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0011_add_workorderstatushistory_model'),
    ]

    operations = [
        migrations.RunSQL(
            sql=STATUS_FLOW_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
