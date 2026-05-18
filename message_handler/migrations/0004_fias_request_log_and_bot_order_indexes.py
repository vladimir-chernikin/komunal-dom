from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("message_handler", "0003_delete_communicativescript"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS fias_request_log (
                id BIGSERIAL PRIMARY KEY,
                request_id UUID NOT NULL,
                session_id VARCHAR(255),
                message_log_id BIGINT,
                state_stage VARCHAR(100),
                method VARCHAR(10) NOT NULL,
                endpoint VARCHAR(255) NOT NULL,
                request_payload JSONB,
                response_payload JSONB,
                http_status INTEGER,
                duration_ms NUMERIC(12, 3),
                error_message TEXT,
                fias_house_guid UUID,
                fias_street_guid UUID,
                building_id INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_fias_request_log_session_created
            ON fias_request_log (session_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_fias_request_log_message
            ON fias_request_log (message_log_id);

            CREATE INDEX IF NOT EXISTS idx_dialog_logs_session_ts_desc
            ON dialog_logs (session_id, timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_address_building_street_house
            ON address.building (street_fias_guid, house_number);

            CREATE INDEX IF NOT EXISTS idx_services_catalog_filter_active
            ON services_catalog (type_id, localization_id, category_id)
            WHERE is_active = TRUE;

            CREATE INDEX IF NOT EXISTS idx_company_period_object_active_dates
            ON company_object_service_period (object_id, date_from, date_to)
            WHERE is_active = TRUE AND is_test = FALSE;
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_company_period_object_active_dates;
            DROP INDEX IF EXISTS idx_services_catalog_filter_active;
            DROP INDEX IF EXISTS idx_address_building_street_house;
            DROP INDEX IF EXISTS idx_dialog_logs_session_ts_desc;
            DROP INDEX IF EXISTS idx_fias_request_log_message;
            DROP INDEX IF EXISTS idx_fias_request_log_session_created;
            DROP TABLE IF EXISTS fias_request_log;
            """,
        )
    ]
