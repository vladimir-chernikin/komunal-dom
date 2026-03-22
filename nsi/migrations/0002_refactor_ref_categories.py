# Generated manually for ref_categories table modernization
# Таблица ref_categories уже существует в БД, меняем структуру напрямую через SQL
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nsi', '0001_initial'),
    ]

    operations = [
        # Удаляем старые поля
        migrations.RunSQL(
            sql="ALTER TABLE ref_categories DROP COLUMN IF EXISTS category_code;",
            reverse_sql="ALTER TABLE ref_categories ADD COLUMN category_code varchar(50);"
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ref_categories DROP COLUMN IF EXISTS description;",
            reverse_sql="ALTER TABLE ref_categories ADD COLUMN description text;"
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ref_categories DROP COLUMN IF EXISTS icon_name;",
            reverse_sql="ALTER TABLE ref_categories ADD COLUMN icon_name varchar(50);"
        ),

        # Добавляем новые поля
        migrations.RunSQL(
            sql="ALTER TABLE ref_categories ADD COLUMN llm_description text NOT NULL DEFAULT '';",
            reverse_sql="ALTER TABLE ref_categories DROP COLUMN llm_description;"
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ref_categories ADD COLUMN is_default boolean NOT NULL DEFAULT false;",
            reverse_sql="ALTER TABLE ref_categories DROP COLUMN is_default;"
        ),
        migrations.RunSQL(
            sql="ALTER TABLE ref_categories ADD COLUMN dev_notes text NULL;",
            reverse_sql="ALTER TABLE ref_categories DROP COLUMN dev_notes;"
        ),

        # Создаем partial unique index для обеспечения единственности is_default=True
        migrations.RunSQL(
            sql="CREATE UNIQUE INDEX ref_categories_default_idx ON ref_categories ((1)) WHERE is_default = true;",
            reverse_sql="DROP INDEX IF EXISTS ref_categories_default_idx;"
        ),
    ]
