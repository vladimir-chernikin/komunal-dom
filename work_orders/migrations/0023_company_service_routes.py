from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0024_drop_file_manager"),
        ("work_orders", "0022_enforce_sla_unique_company_service_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="companydepartment",
            name="is_external",
            field=models.BooleanField(default=False, verbose_name="Внешняя организация"),
        ),
        migrations.AddField(
            model_name="companyroutemapping",
            name="service",
            field=models.ForeignKey(
                blank=True,
                db_column="service_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="company_route_mappings",
                to="portal.servicescatalog",
                verbose_name="Услуга",
            ),
        ),
        migrations.AlterField(
            model_name="companyroutemapping",
            name="route",
            field=models.ForeignKey(
                blank=True,
                db_column="route_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="company_mappings",
                to="work_orders.routeref",
                verbose_name="Типовой маршрут (устарело)",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="companyroutemapping",
            name="uq_company_route_mapping_company_route",
        ),
        migrations.AddConstraint(
            model_name="companyroutemapping",
            constraint=models.UniqueConstraint(
                condition=models.Q(service__isnull=False, is_active=True),
                fields=("company", "service"),
                name="uq_company_service_route_active",
            ),
        ),
        migrations.AddIndex(
            model_name="companyroutemapping",
            index=models.Index(fields=["service"], name="idx_comp_route_map_service"),
        ),
    ]
