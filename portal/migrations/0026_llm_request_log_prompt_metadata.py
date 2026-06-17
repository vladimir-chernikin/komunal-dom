from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0025_delete_aiprompt"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE llm_request_log
                    RENAME COLUMN service_name TO caller_service;

                ALTER TABLE llm_request_log
                    ADD COLUMN prompt_slug varchar(100);

                ALTER TABLE llm_request_log
                    ADD COLUMN prompt_source varchar(50);

                UPDATE llm_request_log
                SET prompt_source = 'legacy'
                WHERE prompt_source IS NULL;

                ALTER TABLE llm_request_log
                    ALTER COLUMN prompt_source SET NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_llm_request_log_caller_service
                    ON llm_request_log (caller_service);

                CREATE INDEX IF NOT EXISTS idx_llm_request_log_prompt_slug
                    ON llm_request_log (prompt_slug);

                CREATE INDEX IF NOT EXISTS idx_llm_request_log_prompt_source
                    ON llm_request_log (prompt_source);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_llm_request_log_prompt_source;
                DROP INDEX IF EXISTS idx_llm_request_log_prompt_slug;
                DROP INDEX IF EXISTS idx_llm_request_log_caller_service;

                ALTER TABLE llm_request_log
                    DROP COLUMN IF EXISTS prompt_source;

                ALTER TABLE llm_request_log
                    DROP COLUMN IF EXISTS prompt_slug;

                ALTER TABLE llm_request_log
                    RENAME COLUMN caller_service TO service_name;
            """,
        ),
    ]
