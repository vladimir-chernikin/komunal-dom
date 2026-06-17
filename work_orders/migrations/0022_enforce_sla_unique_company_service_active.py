from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0021_remove_intake_and_unused_models"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="slapolicy",
            name="uq_sla_policy_company_service_active",
        ),
        migrations.AddConstraint(
            model_name="slapolicy",
            constraint=models.UniqueConstraint(
                fields=("company", "service", "is_active"),
                name="uq_sla_policy_company_service_active",
            ),
        ),
    ]
