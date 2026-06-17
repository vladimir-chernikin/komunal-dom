from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0013_cleanup_sla_and_add_company_sequence_numbers'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='slapolicy',
            name='ck_sla_policy_source',
        ),
        migrations.RemoveField(
            model_name='slapolicy',
            name='policy_source',
        ),
    ]
