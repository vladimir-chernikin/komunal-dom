#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit-тесты для проверки структуры БД services_catalog
Защита от ошибок несовпадения колонок
"""

import os
import sys
import django

# Настройка Django
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from django.db import connection
import unittest
import logging

logger = logging.getLogger(__name__)


class TestDatabaseSchema(unittest.TestCase):
    """Тесты для проверки структуры БД"""

    def setUp(self):
        """Настройка перед каждым тестом"""
        self.cursor = connection.cursor()

    def test_services_catalog_columns(self):
        """Проверка наличия колонок в services_catalog"""
        self.cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'services_catalog'
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in self.cursor.fetchall()]

        required_columns = [
            'service_id', 'scenario_id', 'scenario_name', 'type_id',
            'kind_id', 'localization_id', 'category_id', 'object_id',
            'payment_id', 'route_id', 'urgency_id', 'description_for_search',
            'is_active'
        ]

        for col in required_columns:
            self.assertIn(col, columns, f"Колонка {col} не найдена в services_catalog")

        logger.info(f"✅ services_catalog имеет {len(columns)} колонок")

    def test_ref_tables_exist(self):
        """Проверка наличия справочных таблиц"""
        ref_tables = [
            'ref_service_types',
            'ref_service_kinds',
            'ref_categories',
            'ref_objects',
            'ref_localization',
            'ref_tags'
        ]

        for table in ref_tables:
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, [table])
            exists = self.cursor.fetchone()[0]
            self.assertTrue(exists, f"Справочная таблица {table} не найдена")

        logger.info(f"✅ Все {len(ref_tables)} справочных таблиц существуют")

    def test_ref_tables_have_name_columns(self):
        """Проверка что ref таблицы имеют *_name колонки"""
        expected = {
            'ref_service_types': 'type_name',
            'ref_service_kinds': 'kind_name',
            'ref_categories': 'category_name',
            'ref_objects': 'object_name',
            'ref_localization': 'localization_name',
            'ref_tags': 'tag_name'
        }

        for table, name_col in expected.items():
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                )
            """, [table, name_col])
            exists = self.cursor.fetchone()[0]
            self.assertTrue(exists, f"Колонка {name_col} не найдена в {table}")

        logger.info(f"✅ Все {len(expected)} *_name колонки существуют")

    def test_foreign_keys_to_ref_tables(self):
        """Проверка внешних ключей на ref таблицы"""
        expected_fks = {
            'type_id': 'ref_service_types',
            'kind_id': 'ref_service_kinds',
            'category_id': 'ref_categories',
            'object_id': 'ref_objects',
            'localization_id': 'ref_localization'
        }

        for fk_col, ref_table in expected_fks.items():
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                    WHERE tc.table_name = 'services_catalog'
                      AND kcu.column_name = %s
                      AND tc.constraint_type = 'FOREIGN KEY'
                )
            """, [fk_col])
            exists = self.cursor.fetchone()[0]
            self.assertTrue(exists, f"FK на {ref_table} по колонке {fk_col} не найден")

        logger.info(f"✅ Все {len(expected_fks)} внешних ключей существуют")

    def test_trigram_indexes_exist(self):
        """Проверка наличия триграммных индексов"""
        self.cursor.execute("""
            SELECT tablename, indexdef
            FROM pg_indexes
            WHERE indexdef LIKE '%gin_trgm_ops%'
            ORDER BY tablename
        """)
        trgm_indexes = self.cursor.fetchall()

        # Проверяем что есть индексы на нужных таблицах/колонках
        index_checks = [
            ('services_catalog', 'scenario_name'),
            ('services_catalog', 'description_for_search'),
            ('ref_tags', 'tag_name'),
            ('ref_categories', 'category_name'),
            ('ref_objects', 'object_name')
        ]

        for table, column in index_checks:
            found = False
            for idx_table, idx_def in trgm_indexes:
                if idx_table == table and column in idx_def:
                    found = True
                    break
            self.assertTrue(found, f"Триграммный индекс на {table}.{column} не найден")

        logger.info(f"✅ Все {len(index_checks)} триграммных индексов существуют (всего найдено: {len(trgm_indexes)})")

    def test_services_data_integrity(self):
        """Проверка целостности данных"""
        # Проверка что все услуги имеют обязательные FK
        self.cursor.execute("""
            SELECT COUNT(*)
            FROM services_catalog sc
            LEFT JOIN ref_service_types rt ON sc.type_id = rt.type_id
            LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
            LEFT JOIN ref_objects ro ON sc.object_id = ro.object_id
            WHERE rt.type_id IS NULL
               OR rc.category_id IS NULL
               OR ro.object_id IS NULL
        """)

        null_fks = self.cursor.fetchone()[0]
        self.assertEqual(null_fks, 0, f"Найдено {null_fks} услуг с NULL в обязательных FK")

        # Проверка количества услуг
        self.cursor.execute("SELECT COUNT(*) FROM services_catalog WHERE is_active = TRUE")
        active_services = self.cursor.fetchone()[0]
        self.assertGreater(active_services, 0, "Нет активных услуг в БД")

        logger.info(f"✅ Целостность данных OK: {active_services} активных услуг")

    def test_service_tags_structure(self):
        """Проверка структуры service_tags"""
        # Проверка наличия таблицы
        self.cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'service_tags'
            )
        """)
        exists = self.cursor.fetchone()[0]
        self.assertTrue(exists, "Таблица service_tags не найдена")

        # Проверка колонок
        self.cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'service_tags'
        """)
        columns = [row[0] for row in self.cursor.fetchall()]

        required_columns = ['service_tag_id', 'service_id', 'tag_id', 'tag_weight']
        for col in required_columns:
            self.assertIn(col, columns, f"Колонка {col} не найдена в service_tags")

        # Проверка количества связей
        self.cursor.execute("SELECT COUNT(*) FROM service_tags")
        tags_count = self.cursor.fetchone()[0]
        logger.info(f"✅ service_tags OK: {tags_count} связей")


def run_tests():
    """Запуск всех тестов"""
    print("=" * 70)
    print("ЗАПУСК UNIT-ТЕСТОВ ДЛЯ ПРОВЕРКИ СТРУКТУРЫ БД")
    print("=" * 70)

    # Создаем тест-сьют
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDatabaseSchema)

    # Запускаем
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Итог
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛИЛИСЬ!")
        print(f"Ошибок: {len(result.failures)}")
        print(f"Провалов: {len(result.errors)}")
    print("=" * 70)

    return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
