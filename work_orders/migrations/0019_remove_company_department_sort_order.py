from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("work_orders", "0018_add_single_open_company_period_constraint"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="companydepartment",
            options={
                "ordering": ["company", "parent_department_id", "department_name", "id"],
                "verbose_name": "Подразделение компании",
                "verbose_name_plural": "Подразделения компаний",
            },
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="DROP INDEX IF EXISTS idx_company_department_sort",
                    reverse_sql=(
                        "CREATE INDEX IF NOT EXISTS idx_company_department_sort "
                        "ON company_department (company_id, sort_order)"
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="companydepartment",
                    name="idx_company_department_sort",
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE company_department DROP COLUMN IF EXISTS sort_order",
                    reverse_sql=(
                        "ALTER TABLE company_department "
                        "ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 100"
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="companydepartment",
                    name="sort_order",
                ),
            ],
        ),
    ]
