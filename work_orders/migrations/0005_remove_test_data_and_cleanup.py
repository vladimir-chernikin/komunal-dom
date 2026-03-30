"""
Миграция: Удаление тестовых данных и внешних статусов

Подготовка к рефакторингу модели WorkOrderStatusRef:
1. Удаление всех тестовых заявок и связанных данных
2. Удаление внешних статусов
"""
from django.db import migrations


def delete_test_data_and_external_statuses(apps, schema_editor):
    """Удаляем все тестовые данные и внешние статусы через SQL"""
    # Удаляем в правильном порядке (с учетом FK)
    schema_editor.execute("""
        DELETE FROM request_mgmt.work_order_attachment
        WHERE work_order_id IN (SELECT id FROM request_mgmt.work_order WHERE is_test = true);
    """)

    schema_editor.execute("""
        DELETE FROM request_mgmt.work_order_event_log
        WHERE work_order_id IN (SELECT id FROM request_mgmt.work_order WHERE is_test = true);
    """)

    schema_editor.execute("""
        DELETE FROM request_mgmt.sla_instance
        WHERE work_order_id IN (SELECT id FROM request_mgmt.work_order WHERE is_test = true);
    """)

    schema_editor.execute("""
        DELETE FROM request_mgmt.notification_outbox
        WHERE work_order_id IN (SELECT id FROM request_mgmt.work_order WHERE is_test = true);
    """)

    schema_editor.execute("""
        DELETE FROM request_mgmt.work_order WHERE is_test = true;
    """)

    schema_editor.execute("""
        DELETE FROM request_mgmt.request_intake WHERE is_test = true;
    """)

    # Удаляем переходы, связанные с внешними статусами
    schema_editor.execute("""
        DELETE FROM request_mgmt.work_order_status_transition
        WHERE from_status_id IN (SELECT id FROM request_mgmt.work_order_status_ref WHERE status_scope = 'external')
           OR to_status_id IN (SELECT id FROM request_mgmt.work_order_status_ref WHERE status_scope = 'external');
    """)

    # Удаляем внешние статусы
    schema_editor.execute("""
        DELETE FROM request_mgmt.work_order_status_ref WHERE status_scope = 'external';
    """)


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0004_starter_data'),
    ]

    operations = [
        migrations.RunPython(delete_test_data_and_external_statuses, migrations.RunPython.noop),
    ]
