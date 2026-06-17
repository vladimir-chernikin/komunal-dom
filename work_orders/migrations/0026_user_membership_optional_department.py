from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0025_company_service_route_and_optional_department"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usercompanymembership",
            name="department",
            field=models.ForeignKey(
                blank=True,
                db_column="department_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_memberships",
                to="work_orders.companydepartment",
                verbose_name="Подразделение",
            ),
        ),
    ]
