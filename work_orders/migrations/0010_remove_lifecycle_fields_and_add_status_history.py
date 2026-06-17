# Generated manually - using ONLY RunSQL to avoid Django model/table resolution issues

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('work_orders', '0009_create_15_demo_work_orders'),
    ]

    operations = [
        # SQL commands для создания таблицы истории статусов
        migrations.RunSQL(
            sql="""
            CREATE TABLE work_order_status_history (
                id BIGSERIAL PRIMARY KEY,
                work_order_id BIGINT NOT NULL REFERENCES work_order(id) ON DELETE CASCADE,
                status_id BIGINT NOT NULL REFERENCES work_order_status_ref(id) ON DELETE RESTRICT,
                changed_by_id INT REFERENCES auth_user(id) ON DELETE SET NULL,
                changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                is_test BOOLEAN NOT NULL DEFAULT FALSE
            );

            CREATE INDEX idx_status_hist_work_time ON work_order_status_history(work_order_id, changed_at DESC);
            CREATE INDEX idx_status_hist_status ON work_order_status_history(status_id);
            CREATE INDEX idx_status_hist_user ON work_order_status_history(changed_by_id);

            COMMENT ON TABLE work_order_status_history IS 'История изменения статусов заявки';
            """,
            reverse_sql="""
            DROP TABLE IF EXISTS work_order_status_history CASCADE;
            """
        ),
        # SQL команды для удаления полей
        migrations.RunSQL(
            sql="""
            ALTER TABLE work_order DROP COLUMN IF EXISTS assigned_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS accepted_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS in_progress_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS resident_contacted_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS localized_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS completed_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS closed_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS cancelled_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS reopened_at CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS updated_at CASCADE;

            ALTER TABLE work_order DROP COLUMN IF EXISTS completed_by_user_id CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS closed_by_user_id CASCADE;
            ALTER TABLE work_order DROP COLUMN IF EXISTS cancelled_by_user_id CASCADE;

            ALTER TABLE work_order DROP COLUMN IF EXISTS current_external_status_id CASCADE;

            ALTER TABLE work_order DROP CONSTRAINT IF EXISTS ck_work_order_close_requires_complete_or_cancel CASCADE;
            ALTER TABLE work_order DROP CONSTRAINT IF EXISTS ck_work_order_complete_requires_resolution CASCADE;
            """,
            reverse_sql="""
            -- Нет обратной миграции
            SELECT 1;
            """
        ),
    ]
