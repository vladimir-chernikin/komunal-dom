# -*- coding: utf-8 -*-
"""
Management команда для импорта категорий из Excel файла categories.xlsx

Использование:
    python manage.py import_categories

Файл должен находиться в папке /var/www/komunal-dom_ru/obmen/categories.xlsx

Структура Excel файла:
- Колонка "ID" - ID категории (целое число)
- Колонка "Категория" - Наименование категории (строка)
- Колонка "Переработанное для LLM" - Описание для AI-системы (текст)

Логика:
1. Полностью очищает таблицу ref_categories
2. Импортирует данные из Excel
3. Обрабатывает дубликаты ID (перенумерует конфликтующие ID)
4. Выводит список всех категорий
5. Запрашивает ID категории по умолчанию
"""

import os
import sys
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from nsi.models import RefCategory


class Command(BaseCommand):
    help = 'Импортирует категории из Excel файла в ref_categories'

    def add_arguments(self, parser):
        parser.add_argument(
            '--default-id',
            type=int,
            help='ID категории, которая будет помечена как "по умолчанию"',
            default=None
        )

    def handle(self, *args, **options):
        default_id = options.get('default_id')
        # Путь к Excel файлу
        excel_file = Path('/obmen/categories.xlsx')

        # Проверяем наличие файла
        if not excel_file.exists():
            self.stdout.write(self.style.ERROR(f'Файл не найден: {excel_file}'))
            self.stdout.write('Пожалуйста, поместите файл categories.xlsx в папку obmen/')
            sys.exit(1)

        # Проверяем наличие openpyxl
        try:
            import openpyxl
        except ImportError:
            self.stdout.write(self.style.ERROR('Библиотека openpyxl не установлена'))
            self.stdout.write('Установите её: pip install openpyxl')
            sys.exit(1)

        # Читаем Excel файл
        self.stdout.write(f'Чтение файла: {excel_file}')
        try:
            wb = openpyxl.load_workbook(excel_file, read_only=True)
            sheet = wb.active
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка чтения Excel файла: {e}'))
            sys.exit(1)

        # Получаем данные из Excel
        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) < 2:
            self.stdout.write(self.style.ERROR('Excel файл пустой или содержит только заголовок'))
            sys.exit(1)

        # Заголовки
        headers = [str(h).strip() if h else '' for h in rows[0]]
        self.stdout.write(f'Заголовки: {headers}')

        # Ищем индексы колонок
        try:
            id_idx = headers.index('ID')
            name_idx = headers.index('Категория')
            llm_idx = headers.index('Переработанное для LLM')
        except ValueError as e:
            self.stdout.write(self.style.ERROR(f'Не найдена требуемая колонка: {e}'))
            self.stdout.write('Требуемые колонки: "ID", "Категория", "Переработанное для LLM"')
            sys.exit(1)

        # Собираем данные (пропускаем заголовок)
        data = []
        for row in rows[1:]:
            if not any(row):  # Пропускаем пустые строки
                continue

            category_id = row[id_idx]
            category_name = row[name_idx] if name_idx < len(row) else None
            llm_description = row[llm_idx] if llm_idx < len(row) else None

            # Пропускаем строки без ID
            if category_id is None:
                continue

            # Нормализация данных
            try:
                category_id = int(category_id)
            except (ValueError, TypeError):
                self.stdout.write(self.style.WARNING(f'Пропускаем строку с некорректным ID: {category_id}'))
                continue

            category_name = str(category_name).strip() if category_name else ''
            llm_description = str(llm_description).strip() if llm_description else ''

            # Пропускаем строки без названия
            if not category_name:
                self.stdout.write(self.style.WARNING(f'Пропускаем ID {category_id} без названия'))
                continue

            data.append({
                'category_id': category_id,
                'category_name': category_name,
                'llm_description': llm_description,
            })

        if not data:
            self.stdout.write(self.style.ERROR('Нет данных для импорта'))
            sys.exit(1)

        self.stdout.write(f'Найдено записей: {len(data)}')

        # Очищаем таблицу (временно отключаем foreign key check)
        self.stdout.write('Очистка таблицы ref_categories...')
        from django.db import connection
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Временно отключаем foreign key constraint
                cursor.execute("ALTER TABLE services_catalog DROP CONSTRAINT IF EXISTS services_catalog_category_id_fkey;")
                # Удаляем все категории
                cursor.execute("DELETE FROM ref_categories;")
                # Пересоздаём sequence
                cursor.execute("ALTER SEQUENCE ref_categories_category_id_seq RESTART WITH 1;")

        # Проверяем дубликаты ID и перенумеруем их
        seen_ids = set()
        remap = {}
        next_id = max(d['category_id'] for d in data) + 1

        for item in data:
            original_id = item['category_id']
            if original_id in seen_ids:
                # Дубликат ID - перенумеровываем
                new_id = next_id
                remap[original_id] = new_id
                item['category_id'] = new_id
                next_id += 1
                self.stdout.write(f'  Перенумерован дубликат: ID {original_id} → {new_id}')
            seen_ids.add(item['category_id'])

        if remap:
            self.stdout.write(self.style.WARNING(f'Карта перенумерации: {remap}'))

        # Импортируем данные
        self.stdout.write('Импорт данных...')
        with transaction.atomic():
            for item in data:
                RefCategory.objects.create(
                    category_id=item['category_id'],
                    category_name=item['category_name'],
                    llm_description=item['llm_description'],
                    is_default=False,
                    dev_notes=None,
                )

        self.stdout.write(self.style.SUCCESS(f'Успешно импортировано: {len(data)} категорий'))

        # Выводим все категории
        self.stdout.write('\n' + '='*80)
        self.stdout.write('СПИСОК ВСЕХ КАТЕГОРИЙ:')
        self.stdout.write('='*80)

        categories = RefCategory.objects.all().order_by('category_id')
        for cat in categories:
            self.stdout.write(f'  {cat.category_id} + "{cat.category_name}"')

        self.stdout.write('='*80 + '\n')

        # Установка категории по умолчанию
        if default_id is not None:
            try:
                category = RefCategory.objects.get(category_id=default_id)

                # Сбрасываем is_default у всех
                RefCategory.objects.all().update(is_default=False)

                # Устанавливаем is_default=True для выбранной
                category.is_default = True
                category.save()

                self.stdout.write(self.style.SUCCESS(
                    f'✓ Категория "{category.category_name}" (ID: {default_id}) помечена как по умолчанию'
                ))
            except RefCategory.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Категория с ID {default_id} не найдена'))
        else:
            self.stdout.write('Категория по умолчанию не установлена (используйте --default-id для установки)')

        self.stdout.write(self.style.SUCCESS('ГОТОВО!'))
