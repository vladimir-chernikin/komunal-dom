# Generated manually to restore missing migration
# This migration was already applied to database
# Original file was lost, recreating as dummy migration

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('portal', '0009_remove_keywords_field'),
    ]

    operations = [
        # This migration was already applied - adding timezone field
        # Dummy operation to satisfy Django
        migrations.RunSQL(sql="", reverse_sql=""),
    ]
