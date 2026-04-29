from django.db import migrations

BACKFILL_BUILDINGS_SQL = """
INSERT INTO address.building (id, fias_guid, street_fias_guid, house_number, full_address, created_at, updated_at, created_by_id)
SELECT b.id, b.fias_object_guid, ao.fias_object_guid, upper(trim(b.house_number)),
       COALESCE(NULLIF(b.fias_full_name, ''), concat_ws(', ', NULLIF(concat('г ', parent2.name), 'г '), NULLIF(concat('ул ', ao.name), 'ул '), NULLIF(concat('д ', upper(trim(b.house_number))), 'д '))),
       b.created_at, b.updated_at, b.created_by_id
FROM kladr_building b
JOIN kladr_kladraddressobject ao ON ao.id = b.address_object_id
LEFT JOIN kladr_kladraddressobject parent1 ON parent1.id = ao.parent_id
LEFT JOIN kladr_kladraddressobject parent2 ON parent2.id = parent1.parent_id
ON CONFLICT (id) DO UPDATE
SET fias_guid = EXCLUDED.fias_guid, street_fias_guid = EXCLUDED.street_fias_guid, house_number = EXCLUDED.house_number, full_address = EXCLUDED.full_address, updated_at = EXCLUDED.updated_at, created_by_id = EXCLUDED.created_by_id;
"""
BACKFILL_UNITS_SQL = """
INSERT INTO address.unit (id, building_id, unit_number, created_at, updated_at)
SELECT u.unit_id, u.building_id, upper(trim(u.unit_number)), NOW(), NOW()
FROM units u
WHERE u.building_id IS NOT NULL AND COALESCE(trim(u.unit_number), '') <> ''
ON CONFLICT (id) DO UPDATE
SET building_id = EXCLUDED.building_id, unit_number = EXCLUDED.unit_number, updated_at = NOW();
"""
RESET_SEQUENCES_SQL = """
SELECT setval(pg_get_serial_sequence('address.building', 'id'), COALESCE((SELECT MAX(id) FROM address.building), 1), true);
SELECT setval(pg_get_serial_sequence('address.unit', 'id'), COALESCE((SELECT MAX(id) FROM address.unit), 1), true);
"""
class Migration(migrations.Migration):
    dependencies = [('address', '0001_initial')]
    operations = [
        migrations.RunSQL(BACKFILL_BUILDINGS_SQL, reverse_sql='DELETE FROM address.building;'),
        migrations.RunSQL(BACKFILL_UNITS_SQL, reverse_sql='DELETE FROM address.unit;'),
        migrations.RunSQL(RESET_SEQUENCES_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
