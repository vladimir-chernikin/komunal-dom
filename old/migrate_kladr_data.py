"""
Скрипт миграции данных KLADR из старых таблиц в новые Django модели.

Старые таблицы → Новые таблицы:
- kladr_types → kladr_kladrobjecttype
- kladr_address_objects → kladr_kladraddressobject

Дата: 2025-12-25
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from django.db import connection, transaction
from kladr.models import KladrObjectType, KladrAddressObject


def migrate_kladr_types():
    """Миграция типов объектов KLADR"""
    print("=" * 60)
    print("ШАГ 1: Миграция kladr_types → kladr_kladrobjecttype")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Проверяем исходные данные
        cursor.execute("SELECT COUNT(*) FROM kladr_types")
        old_count = cursor.fetchone()[0]
        print(f"Исходных записей: {old_count}")

        # Проверяем целевые данные
        cursor.execute("SELECT COUNT(*) FROM kladr_kladrobjecttype")
        new_count = cursor.fetchone()[0]
        print(f"Текущих записей в новой таблице: {new_count}")

        if old_count == 0:
            print("⚠️  В исходной таблице нет данных!")
            return False

        # Получаем данные из старой таблицы
        cursor.execute("""
            SELECT
                type_id,
                type_short,
                type_full
            FROM kladr_types
            ORDER BY type_id
        """)

        old_types = cursor.fetchall()
        print(f"Получено записей: {len(old_types)}")

        # Вставляем в новую таблицу с маппингом полей
        # type_id → id
        # type_short → code
        # type_full → name
        # level → вычисляем на основе типа
        # short_name → type_short

        level_mapping = {
            'обл': 1,      # Регион
            'край': 1,     # Регион
            'АО': 1,       # Регион (автономный округ)
            'Респ': 1,     # Регион (республика)
            'Аобл': 1,     # Регион (автономная область)
            'р-н': 2,      # Район
            'г': 3,        # Город
            'п': 4,        # Населенный пункт
            'ул': 5,       # Улица
            'д': 6,        # Здание
        }

        inserted = 0
        errors = []

        for type_id, type_short, type_full in old_types:
            try:
                # Определяем уровень по типу
                level = level_mapping.get(type_short, 4)  # Default: населенный пункт

                cursor.execute("""
                    INSERT INTO kladr_kladrobjecttype
                        (id, code, name, level, short_name)
                    VALUES
                        (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        code = EXCLUDED.code,
                        name = EXCLUDED.name,
                        level = EXCLUDED.level,
                        short_name = EXCLUDED.short_name
                """, (type_id, type_short, type_full, level, type_short))

                inserted += 1
                print(f"  ✓ {type_id}: {type_full} (уровень {level})")

            except Exception as e:
                errors.append(f"Ошибка типа {type_id}: {e}")
                print(f"  ✗ Ошибка типа {type_id}: {e}")

        print(f"\n✅ Успешно мигрировано: {inserted}/{len(old_types)}")
        if errors:
            print(f"❌ Ошибок: {len(errors)}")
            for error in errors[:5]:  # Показываем первые 5 ошибок
                print(f"   - {error}")

        return inserted > 0


def migrate_kladr_address_objects():
    """Миграция адресных объектов KLADR"""
    print("\n" + "=" * 60)
    print("ШАГ 2: Миграция kladr_address_objects → kladr_kladraddressobject")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Проверяем исходные данные
        cursor.execute("SELECT COUNT(*) FROM kladr_address_objects")
        old_count = cursor.fetchone()[0]
        print(f"Исходных записей: {old_count}")

        # Проверяем целевые данные
        cursor.execute("SELECT COUNT(*) FROM kladr_kladraddressobject")
        new_count = cursor.fetchone()[0]
        print(f"Текущих записей в новой таблице: {new_count}")

        if old_count == 0:
            print("⚠️  В исходной таблице нет данных!")
            return False

        # Получаем данные из старой таблицы
        cursor.execute("""
            SELECT
                ao_id,
                name,
                type_id,
                parent_ao_id,
                kladr_code,
                kladr_level
            FROM kladr_address_objects
            ORDER BY kladr_level, name
        """)

        old_objects = cursor.fetchall()
        print(f"Получено записей: {len(old_objects)}")

        # Вставляем в новую таблицу с маппингом полей
        # ao_id → id
        # name → name
        # type_id → type (ForeignKey на kladr_kladrobjecttype)
        # parent_ao_id → parent (ForeignKey на саму себя)
        # kladr_code → code
        # zip_code → NULL (нет в старой таблице)
        # okato → NULL (нет в старой таблице)
        # oktmo → NULL (нет в старой таблице)
        # is_active → TRUE (по умолчанию)

        inserted = 0
        errors = []

        for ao_id, name, type_id, parent_ao_id, kladr_code, kladr_level in old_objects:
            try:
                # Проверяем, существует ли type_id в новой таблице
                cursor.execute("SELECT id FROM kladr_kladrobjecttype WHERE id = %s", (type_id,))
                if not cursor.fetchone():
                    errors.append(f"Объект {ao_id}: type_id={type_id} не существует в kladr_kladrobjecttype")
                    print(f"  ✗ Объект {ao_id}: type_id={type_id} не найден (пропущен)")
                    continue

                # Если есть parent, проверяем его существование
                if parent_ao_id:
                    cursor.execute("SELECT id FROM kladr_kladraddressobject WHERE id = %s", (parent_ao_id,))
                    if not cursor.fetchone():
                        errors.append(f"Объект {ao_id}: parent_ao_id={parent_ao_id} еще не мигрирован")
                        print(f"  ⚠ Объект {ao_id}: parent={parent_ao_id} еще не мигрирован (будет NULL)")
                        parent_ao_id = None

                # Обрабатываем NULL для kladr_code - генерируем из ao_id
                code_value = kladr_code if kladr_code else f"CODE_{ao_id}"

                cursor.execute("""
                    INSERT INTO kladr_kladraddressobject
                        (id, name, code, type_id, parent_id, zip_code, okato, oktmo, is_active, created_at, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        code = EXCLUDED.code,
                        type_id = EXCLUDED.type_id,
                        parent_id = EXCLUDED.parent_id,
                        is_active = EXCLUDED.is_active,
                        updated_at = NOW()
                """, (ao_id, name, code_value, type_id, parent_ao_id, None, None, None, True))

                inserted += 1
                print(f"  ✓ {ao_id}: {name} (код: {kladr_code})")

            except Exception as e:
                errors.append(f"Ошибка объекта {ao_id}: {e}")
                print(f"  ✗ Ошибка объекта {ao_id}: {e}")

        print(f"\n✅ Успешно мигрировано: {inserted}/{len(old_objects)}")
        if errors:
            print(f"❌ Ошибок: {len(errors)}")
            for error in errors[:5]:  # Показываем первые 5 ошибок
                print(f"   - {error}")

        return inserted > 0


def verify_migration():
    """Проверка результатов миграции"""
    print("\n" + "=" * 60)
    print("ШАГ 3: Проверка результатов миграции")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Проверяем количество записей
        cursor.execute("SELECT COUNT(*) FROM kladr_kladrobjecttype")
        types_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM kladr_kladraddressobject")
        objects_count = cursor.fetchone()[0]

        print(f"kladr_kladrobjecttype: {types_count} записей")
        print(f"kladr_kladraddressobject: {objects_count} записей")

        # Проверяем через Django ORM
        print("\nПроверка через Django ORM:")
        django_types = KladrObjectType.objects.count()
        django_objects = KladrAddressObject.objects.count()

        print(f"KladrObjectType.objects.count(): {django_types}")
        print(f"KladrAddressObject.objects.count(): {django_objects}")

        # Показываем примеры данных
        print("\nПримеры типов:")
        for t in KladrObjectType.objects.all()[:5]:
            print(f"  - {t.name} (уровень {t.level})")

        print("\nПримеры адресных объектов:")
        for obj in KladrAddressObject.objects.all()[:5]:
            parent_info = f", родитель: {obj.parent.name}" if obj.parent else ""
            print(f"  - {obj.name} ({obj.type.name}){parent_info}")

        success = (types_count > 0 and objects_count > 0)
        if success:
            print("\n✅ Миграция завершена успешно!")
        else:
            print("\n❌ Миграция не выполнена или данные отсутствуют")

        return success


def main():
    """Главная функция миграции"""
    print("=" * 60)
    print("МИГРАЦИЯ ДАННЫХ KLADR")
    print("=" * 60)
    print()

    try:
        with transaction.atomic():
            # Шаг 1: Миграция типов
            types_success = migrate_kladr_types()

            if not types_success:
                print("\n❌ Ошибка миграции типов!")
                return

            # Шаг 2: Миграция адресных объектов
            objects_success = migrate_kladr_address_objects()

            if not objects_success:
                print("\n❌ Ошибка миграции адресных объектов!")
                return

            # Шаг 3: Проверка
            verify_migration()

    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("МИГРАЦИЯ ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":
    main()
