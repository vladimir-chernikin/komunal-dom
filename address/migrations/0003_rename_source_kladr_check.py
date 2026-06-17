from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("address", "0002_backfill_from_kladr"),
    ]

    operations = [
        migrations.RenameField(
            model_name="importrow",
            old_name="source_kladr_check",
            new_name="building_fias_guid",
        ),
        migrations.AlterField(
            model_name="importrow",
            name="building_fias_guid",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
    ]
