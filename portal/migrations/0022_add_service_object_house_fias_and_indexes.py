from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0021_merge_0016_0020"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE service_objects
                ADD COLUMN IF NOT EXISTS fias_house_object_id bigint;

                UPDATE service_objects AS so
                SET fias_house_object_id = kb.fias_object_id
                FROM kladr_building AS kb
                WHERE so.building_id = kb.id
                  AND kb.fias_object_id IS NOT NULL
                  AND (
                      so.fias_house_object_id IS NULL
                      OR so.fias_house_object_id <> kb.fias_object_id
                  );

                CREATE INDEX IF NOT EXISTS idx_srvobj_building
                    ON service_objects (building_id);

                CREATE INDEX IF NOT EXISTS idx_srvobj_fias_house
                    ON service_objects (fias_house_object_id);

                CREATE INDEX IF NOT EXISTS idx_srvobj_building_active
                    ON service_objects (building_id, is_active);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_srvobj_building_active;
                DROP INDEX IF EXISTS idx_srvobj_fias_house;
                DROP INDEX IF EXISTS idx_srvobj_building;
                ALTER TABLE service_objects
                DROP COLUMN IF EXISTS fias_house_object_id;
            """,
        ),
    ]
