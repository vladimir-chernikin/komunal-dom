from django.db import migrations, models
import django.db.models.deletion


def delete_legacy_generic_routes(apps, schema_editor):
    CompanyRouteMapping = apps.get_model("work_orders", "CompanyRouteMapping")
    CompanyRouteMapping.objects.filter(service__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0024_remove_route_ref"),
        ("portal", "0024_drop_file_manager"),
    ]

    operations = [
        migrations.RunPython(delete_legacy_generic_routes, migrations.RunPython.noop),
        migrations.RenameModel(
            old_name="CompanyRouteMapping",
            new_name="CompanyServiceRoute",
        ),
        migrations.AlterModelTable(
            name="companyserviceroute",
            table="company_service_route",
        ),
        migrations.AlterModelOptions(
            name="companyserviceroute",
            options={
                "ordering": ["company", "service", "id"],
                "verbose_name": "Маршрут услуги компании",
                "verbose_name_plural": "Маршруты услуг компании",
            },
        ),
        migrations.AlterField(
            model_name="companyserviceroute",
            name="company",
            field=models.ForeignKey(
                db_column="company_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="service_routes",
                to="nsi.company",
                verbose_name="Компания",
            ),
        ),
        migrations.AlterField(
            model_name="companyserviceroute",
            name="service",
            field=models.ForeignKey(
                db_column="service_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="company_service_routes",
                to="portal.servicescatalog",
                verbose_name="Услуга",
            ),
        ),
        migrations.AlterField(
            model_name="companyserviceroute",
            name="target_department",
            field=models.ForeignKey(
                db_column="target_department_id",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="incoming_service_routes",
                to="work_orders.companydepartment",
                verbose_name="Целевое подразделение",
            ),
        ),
        migrations.AlterField(
            model_name="workorder",
            name="department",
            field=models.ForeignKey(
                blank=True,
                db_column="department_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="work_orders",
                to="work_orders.companydepartment",
                verbose_name="Подразделение",
            ),
        ),
    ]
