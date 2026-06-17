from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0017_remove_sla_priority_dimension"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="companyobjectserviceperiod",
            constraint=models.UniqueConstraint(
                fields=("object",),
                condition=Q(is_active=True, is_test=False, date_to__isnull=True),
                name="uq_comp_obj_period_open_live",
            ),
        ),
    ]
