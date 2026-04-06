# Generated manually for schema migration
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('nsi', '0004_remove_reflocalization_llm_description_and_more'),
        ('portal', '0017_initial_schema'),
    ]

    operations = [
        # Добавляем primary_company (FK на nsi.Company, которая в схеме public)
        migrations.AddField(
            model_name='userprofile',
            name='primary_company',
            field=models.ForeignKey(
                blank=True,
                help_text='Основная компания пользователя для 90% кейсов',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='primary_users',
                to='nsi.company',
                verbose_name='Основная компания'
            ),
        ),
        # Добавляем primary_department через RunSQL с указанием схемы
        migrations.RunSQL(
            sql="""
                ALTER TABLE portal_userprofile
                ADD COLUMN primary_department_id INTEGER NULL;
            """,
            reverse_sql="""
                ALTER TABLE portal_userprofile
                DROP COLUMN primary_department_id;
            """,
        ),
        # Добавляем FK constraint через RunSQL
        migrations.RunSQL(
            sql="""
                ALTER TABLE portal_userprofile
                ADD CONSTRAINT portal_userprofile_primary_department_id_fk
                FOREIGN KEY (primary_department_id)
                REFERENCES request_mgmt.company_department(id)
                ON DELETE SET NULL;
            """,
            reverse_sql="""
                ALTER TABLE portal_userprofile
                DROP CONSTRAINT portal_userprofile_primary_department_id_fk;
            """,
        ),
        # Добавляем comment для primary_department
        migrations.RunSQL(
            sql="""
                COMMENT ON COLUMN portal_userprofile.primary_department_id IS 'Основное подразделение пользователя для 90% кейсов';
            """,
            reverse_sql="",
        ),
    ]
