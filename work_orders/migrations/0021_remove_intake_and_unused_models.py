from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('work_orders', '0020_enforce_unique_company_route_mapping'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='workorder',
            name='request_intake',
        ),
        migrations.DeleteModel(
            name='NotificationOutbox',
        ),
        migrations.DeleteModel(
            name='WorkOrderStatusTransition',
        ),
        migrations.DeleteModel(
            name='RequestIntake',
        ),
    ]
