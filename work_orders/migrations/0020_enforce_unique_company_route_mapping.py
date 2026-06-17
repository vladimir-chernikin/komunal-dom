from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0019_remove_company_department_sort_order"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="companyroutemapping",
            name="uq_company_route_mapping_active_route_per_company",
        ),
        migrations.AddConstraint(
            model_name="companyroutemapping",
            constraint=models.UniqueConstraint(
                fields=("company", "route"),
                name="uq_company_route_mapping_company_route",
            ),
        ),
    ]
