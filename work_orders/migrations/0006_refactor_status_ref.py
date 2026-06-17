"""
Миграция: Рефакторинг модели WorkOrderStatusRef

Изменения:
1. Удаление поля status_scope (Область применения)
2. Добавление поля display_name_for_user (Для пользователя)
3. Изменение verbose_name для is_terminal (Терминальный -> Конечный)
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0005_remove_test_data_and_cleanup'),
    ]

    operations = [
        # Шаг 1: Добавляем новое поле display_name_for_user
        migrations.RunSQL(
            "ALTER TABLE request_mgmt.work_order_status_ref ADD COLUMN display_name_for_user varchar(100) NOT NULL DEFAULT '';",
            reverse_sql="ALTER TABLE request_mgmt.work_order_status_ref DROP COLUMN display_name_for_user;"
        ),
        # Шаг 2: Заполняем его данными
        migrations.RunSQL(
            """
            UPDATE request_mgmt.work_order_status_ref
            SET display_name_for_user = CASE short_code_en
                WHEN 'new_registered' THEN 'Новая'
                WHEN 'accepted_by_executor' THEN 'Принята исполнителем'
                WHEN 'in_progress' THEN 'В работе'
                WHEN 'on_hold' THEN 'Приостановлена'
                WHEN 'completed' THEN 'Выполнена'
                WHEN 'closed' THEN 'Закрыта'
                WHEN 'cancelled' THEN 'Отменена'
                WHEN 'reopened' THEN 'Переоткрыта'
                ELSE short_name_ru
            END;
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
        # Шаг 3: Удаляем поле status_scope
        migrations.RunSQL(
            "ALTER TABLE request_mgmt.work_order_status_ref DROP COLUMN status_scope;",
            reverse_sql=migrations.RunSQL.noop
        ),
        # Шаг 4: Удаляем CHECK constraint для status_scope
        migrations.RunSQL(
            "ALTER TABLE request_mgmt.work_order_status_ref DROP CONSTRAINT IF EXISTS ck_work_order_status_ref_scope;",
            reverse_sql=migrations.RunSQL.noop
        ),
        # Шаг 5: Удаляем индекс для status_scope
        migrations.RunSQL(
            "DROP INDEX IF EXISTS request_mgmt.idx_work_status_ref_scope;",
            reverse_sql=migrations.RunSQL.noop
        ),
    ]
