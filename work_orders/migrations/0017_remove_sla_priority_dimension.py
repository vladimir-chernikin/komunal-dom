from django.db import migrations, models
from django.db.models import Q


def deduplicate_sla_policies(apps, schema_editor):
    SLAPolicy = apps.get_model('work_orders', 'SLAPolicy')
    SLAInstance = apps.get_model('work_orders', 'SLAInstance')

    grouped_keys = (
        SLAPolicy.objects
        .values_list('company_id', 'service_id')
        .distinct()
    )

    for company_id, service_id in grouped_keys:
        policies = list(
            SLAPolicy.objects
            .filter(company_id=company_id, service_id=service_id)
            .order_by('id')
        )
        if len(policies) <= 1:
            continue

        keep_policy = next((policy for policy in policies if policy.is_active), policies[0])
        duplicate_ids = [policy.id for policy in policies if policy.id != keep_policy.id]

        if duplicate_ids:
            SLAInstance.objects.filter(sla_policy_id__in=duplicate_ids).update(sla_policy_id=keep_policy.id)
            SLAPolicy.objects.filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('work_orders', '0016_seed_company_object_service_periods'),
    ]

    operations = [
        migrations.RunPython(deduplicate_sla_policies, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='slapolicy',
            name='uq_sla_policy_company_service_priority',
        ),
        migrations.RemoveField(
            model_name='slapolicy',
            name='priority_code',
        ),
        migrations.AlterModelOptions(
            name='slapolicy',
            options={
                'verbose_name': 'SLA-политика',
                'verbose_name_plural': 'SLA-политики',
                'ordering': ['company', 'service'],
            },
        ),
        migrations.AddConstraint(
            model_name='slapolicy',
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True),
                fields=('company', 'service'),
                name='uq_sla_policy_company_service_active',
            ),
        ),
    ]
