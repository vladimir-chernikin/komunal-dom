"""
Миграция: Удаление внешнего статуса из модели WorkOrder

Изменения:
1. Удаление поля current_external_status (теперь используется только internal)
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0006_refactor_status_ref'),
    ]

    operations = [
        # Удаляем FK constraint
        migrations.RunSQL(
            "ALTER TABLE request_mgmt.work_order DROP CONSTRAINT IF EXISTS work_order_current_external_status_id_fkey;",
            reverse_sql=migrations.RunSQL.noop
        ),
        # Удаляем столбец
        migrations.RunSQL(
            "ALTER TABLE request_mgmt.work_order DROP COLUMN IF EXISTS current_external_status_id;",
            reverse_sql=migrations.RunSQL.noop
        ),
    ]
