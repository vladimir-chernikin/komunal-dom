# Generated manually for data migration
from django.db import migrations


def migrate_primary_company_and_department(apps, schema_editor):
    """
    Перенос данных из UserCompanyMembership в UserProfile

    ПРАВИЛО МИГРАЦИИ:
    Для каждого пользователя без primary_company/primary_department:
    1. Ищем активную запись UserCompanyMembership с is_primary=True и date_to IS NULL
    2. Если нет - берем первую активную запись
    3. Если найдена - копируем company_id и department_id в UserProfile
    """
    # Используем прямой SQL для работы с таблицами в схеме request_mgmt
    with schema_editor.connection.cursor() as cursor:
        # Обновляем UserProfile данными из UserCompanyMembership
        cursor.execute("""
            UPDATE portal_userprofile p
            SET
                primary_company_id = ucm.company_id,
                primary_department_id = ucm.department_id
            FROM request_mgmt.user_company_membership ucm
            WHERE
                p.user_id = ucm.user_id
                AND p.primary_company_id IS NULL
                AND ucm.is_active = true
                AND (ucm.date_to IS NULL OR ucm.date_to > CURRENT_DATE)
                AND ucm.is_primary = true
        """)

        # Для тех, у кого нет is_primary, берем любую активную запись
        cursor.execute("""
            UPDATE portal_userprofile p
            SET
                primary_company_id = ucm.company_id,
                primary_department_id = ucm.department_id
            FROM request_mgmt.user_company_membership ucm
            WHERE
                p.user_id = ucm.user_id
                AND p.primary_company_id IS NULL
                AND ucm.is_active = true
                AND (ucm.date_to IS NULL OR ucm.date_to > CURRENT_DATE)
                AND NOT EXISTS (
                    SELECT 1 FROM request_mgmt.user_company_membership ucm2
                    WHERE ucm2.user_id = p.user_id
                    AND ucm2.is_primary = true
                    AND ucm2.is_active = true
                    AND (ucm2.date_to IS NULL OR ucm2.date_to > CURRENT_DATE)
                )
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0018_add_primary_company_and_department_to_userprofile'),
    ]

    operations = [
        migrations.RunPython(
            migrate_primary_company_and_department,
            migrations.RunPython.noop
        ),
    ]
