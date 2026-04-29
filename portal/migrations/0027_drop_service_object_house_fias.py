from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('portal', '0026_llm_request_log_prompt_metadata'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DROP INDEX IF EXISTS idx_srvobj_fias_house;
                ALTER TABLE service_objects
                DROP COLUMN IF EXISTS fias_house_object_id;
            """,
            reverse_sql="""
                ALTER TABLE service_objects
                ADD COLUMN IF NOT EXISTS fias_house_object_id bigint;
                CREATE INDEX IF NOT EXISTS idx_srvobj_fias_house
                ON service_objects (fias_house_object_id);
            """,
        ),
    ]
