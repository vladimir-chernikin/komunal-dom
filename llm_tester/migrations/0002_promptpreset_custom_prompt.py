# Generated manually to restore missing migration
# This migration was already applied to database
# Original file was lost, recreating as dummy migration

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('llm_tester', '0001_initial'),
    ]

    operations = [
        # This migration was already applied - adding custom_prompt field
        # Dummy operation to satisfy Django
        migrations.RunSQL(sql="", reverse_sql=""),
    ]
