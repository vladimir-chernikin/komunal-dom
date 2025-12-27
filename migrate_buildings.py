"""
Скрипт миграции зданий из старой таблицы в новую Django модель.

Старая таблица → Новая таблица:
- buildings → kladr_building

Дата: 2025-12-25
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from django.db import connection, transaction
from kladr.models import Building


def migrate_buildings():
    """Миграция зданий"""
    print("=" * 60)
    print("МИГРАЦИЯ ЗДАНИЙ: buildings → kladr_building")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Проверяем исходные данные
        cursor.execute("SELECT COUNT(*) FROM buildings")
        old_count = cursor.fetchone()[0]
        print(f"\nИсходных записей: {old_count}")

        # Проверяем целевые данные
        cursor.execute("SELECT COUNT(*) FROM kladr_building")
        new_count = cursor.fetchone()[0]
        print(f"Текущих записей в новой таблице: {new_count}")

        if old_count == 0:
            print("\nВ исходной таблице нет данных!")
            return False

        # Получаем данные из старой таблицы
        cursor.execute("""
            SELECT
                building_id,
                house_number,
                parent_ao_id,
                kladr_code
            FROM buildings
            ORDER BY building_id
        """)

        old_buildings = cursor.fetchall()
        print(f"Получено записей: {len(old_buildings)}")

        # Маппинг полей
        inserted = 0
        errors = []

        for building_id, house_number, parent_ao_id, kladr_code in old_buildings:
            try:
                # Проверяем, существует ли address_object в новой таблице
                cursor.execute("""
                    SELECT name, type_id
                    FROM kladr_kladraddressobject
                    WHERE id = %s
                """, (parent_ao_id,))

                result = cursor.fetchone()
                if not result:
                    errors.append(f"Здание {building_id}: parent_ao_id={parent_ao_id} не существует")
                    print(f"  ✗ Здание {building_id}: parent_ao_id={parent_ao_id} не найден (пропущен)")
                    continue

                street_name, type_id = result

                # Определяем building_type (используем пустую строку вместо NULL)
                building_type = kladr_code if kladr_code else ""

                cursor.execute("""
                    INSERT INTO kladr_building
                        (id, address_object_id, house_number, building_type,
                         porch_count, floor_count, has_elevator, square_total,
                         created_at, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        address_object_id = EXCLUDED.address_object_id,
                        house_number = EXCLUDED.house_number,
                        building_type = EXCLUDED.building_type,
                        updated_at = NOW()
                """, (building_id, parent_ao_id, house_number, building_type,
                      None, None, False, None))

                inserted += 1
                print(f"  ✓ {building_id}: ул. {street_name}, д. {house_number}")

            except Exception as e:
                errors.append(f"Ошибка здания {building_id}: {e}")
                print(f"  ✗ Ошибка здания {building_id}: {e}")

        print(f"\n✅ Успешно мигрировано: {inserted}/{len(old_buildings)}")
        if errors:
            print(f"❌ Ошибок: {len(errors)}")
            for error in errors[:5]:
                print(f"   - {error}")

        return inserted > 0


def verify_migration():
    """Проверка результатов миграции"""
    print("\n" + "=" * 60)
    print("ПРОВЕРКА РЕЗУЛЬТАТОВ")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Проверяем через SQL
        cursor.execute("SELECT COUNT(*) FROM kladr_building")
        buildings_count = cursor.fetchone()[0]

        print(f"\nkladr_building: {buildings_count} записей")

        # Проверяем через Django ORM
        django_count = Building.objects.count()
        print(f"Building.objects.count(): {django_count}")

        if buildings_count == 0:
            print("\n❌ Здания не мигрированы!")
            return False

        # Показываем примеры
        print("\nПримеры зданий:")
        for b in Building.objects.select_related('address_object').all()[:10]:
            parent_info = f" ({b.address_object.name})" if b.address_object else ""
            print(f"  - д. {b.house_number}{parent_info}")

        # Статистика по улицам
        print("\nСтатистика по улицам:")
        cursor.execute("""
            SELECT kao.name, COUNT(*) as building_count
            FROM kladr_building kb
            JOIN kladr_kladraddressobject kao ON kb.address_object_id = kao.id
            GROUP BY kao.name
            ORDER BY building_count DESC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            street_name, count = row
            print(f"  - ул. {street_name}: {count} зд.")

        success = buildings_count > 0
        if success:
            print("\n✅ Миграция завершена успешно!")

        return success


def check_bot_compatibility():
    """Проверка совместимости с ботом"""
    print("\n" + "=" * 60)
    print("ПРОВЕРКА СОВМЕСТИМОСТИ С БОТОМ")
    print("=" * 60)

    with connection.cursor() as cursor:
        # Бот использует СТАРЫЕ таблицы
        print("\nБот использует СТАРУЮ схему:")
        print("  - kladr_address_objects")
        print("  - buildings")

        cursor.execute("""
            SELECT COUNT(DISTINCT ao.ao_id)
            FROM kladr_address_objects ao
            JOIN buildings b ON ao.ao_id = b.parent_ao_id
        """)

        streets_with_buildings = cursor.fetchone()[0]
        print(f"\nУлиц с зданиями (старая схема): {streets_with_buildings}")

        if streets_with_buildings > 0:
            print("✅ Бот сможет находить адреса!")

            cursor.execute("""
                SELECT ao.name, COUNT(*) as building_count
                FROM kladr_address_objects ao
                JOIN buildings b ON ao.ao_id = b.parent_ao_id
                GROUP BY ao.ao_id, ao.name
                ORDER BY building_count DESC
                LIMIT 5
            """)

            print("\nТоп улиц по количеству зданий:")
            for row in cursor.fetchall():
                street_name, count = row
                print(f"  - ул. {street_name}: {count} зд.")
        else:
            print("❌ Бот НЕ сможет находить адресы - нет зданий!")


def main():
    """Главная функция миграции"""
    print("=" * 60)
    print("МИГРАЦИЯ ЗДАНИЙ")
    print("=" * 60)

    try:
        with transaction.atomic():
            # Миграция
            success = migrate_buildings()

            if not success:
                print("\n❌ Миграция не выполнена!")
                return

            # Проверка
            verify_migration()

            # Проверка совместимости с ботом
            check_bot_compatibility()

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
