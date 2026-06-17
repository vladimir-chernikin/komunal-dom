from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0023_company_service_routes"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="workorder",
            name="idx_work_order_route",
        ),
        migrations.RemoveIndex(
            model_name="companyroutemapping",
            name="idx_comp_route_map_route",
        ),
        migrations.RemoveField(
            model_name="workorder",
            name="route",
        ),
        migrations.RemoveField(
            model_name="companyroutemapping",
            name="route",
        ),
        migrations.DeleteModel(
            name="RouteRef",
        ),
    ]
