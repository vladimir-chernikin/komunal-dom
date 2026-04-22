from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0023_delete_semanticpattern'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                (
                    "DELETE FROM auth_permission WHERE content_type_id IN "
                    "(SELECT id FROM django_content_type WHERE app_label = 'file_manager')"
                ),
                "DELETE FROM django_admin_log WHERE content_type_id IN (SELECT id FROM django_content_type WHERE app_label = 'file_manager')",
                "DELETE FROM django_content_type WHERE app_label = 'file_manager'",
                "DROP TABLE IF EXISTS file_manager_userfile CASCADE",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
