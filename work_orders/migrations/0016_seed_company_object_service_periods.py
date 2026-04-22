from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("work_orders", "0015_add_user_company_membership_table"),
        ("portal", "0021_merge_0016_0020"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                INSERT INTO request_mgmt.company_object_service_period (
                    company_id,
                    object_id,
                    date_from,
                    date_to,
                    comment,
                    is_active,
                    created_at,
                    updated_at,
                    is_test
                )
                SELECT
                    c.id,
                    so.service_object_id,
                    COALESCE(so.created_at::date, CURRENT_DATE),
                    NULL,
                    'Первичное заполнение связи объект -> компания для чатового intake',
                    TRUE,
                    NOW(),
                    NOW(),
                    FALSE
                FROM service_objects AS so
                CROSS JOIN LATERAL (
                    SELECT id
                    FROM nsi_company
                    WHERE name = 'ООО УК АСПЕКТ'
                    ORDER BY id
                    LIMIT 1
                ) AS c
                WHERE so.is_active = TRUE
                  AND NOT EXISTS (
                      SELECT 1
                      FROM request_mgmt.company_object_service_period AS p
                      WHERE p.object_id = so.service_object_id
                  );
            """,
            reverse_sql="""
                DELETE FROM request_mgmt.company_object_service_period
                WHERE comment = 'Первичное заполнение связи объект -> компания для чатового intake';
            """,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE request_mgmt.company_object_service_period
                DROP CONSTRAINT IF EXISTS ex_company_object_service_period_no_overlap;

                ALTER TABLE request_mgmt.company_object_service_period
                ADD CONSTRAINT ex_company_object_service_period_no_overlap
                EXCLUDE USING gist (
                    object_id WITH =,
                    daterange(date_from, COALESCE(date_to + 1, 'infinity'::date), '[)') WITH &&
                )
                WHERE (is_active AND NOT is_test);
            """,
            reverse_sql="""
                ALTER TABLE request_mgmt.company_object_service_period
                DROP CONSTRAINT IF EXISTS ex_company_object_service_period_no_overlap;
            """,
        ),
    ]
