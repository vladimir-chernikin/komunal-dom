"""
Django views для СУБД SQL интерфейса

Позволяет просматривать структуру БД, данные таблиц и связи между ними
"""
from django.db import connection
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.core.paginator import Paginator
import json


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def table_list(request):
    """
    Список всех таблиц БД с описанием, количеством записей,
    кнопками 'Структура' и 'Данные'
    """
    with connection.cursor() as cursor:
        # Получаем список всех таблиц
        cursor.execute("""
            SELECT
                t.table_schema,
                t.table_name,
                obj_description((t.table_schema||'.'||t.table_name)::regclass, 'pg_class') as description,
                (SELECT count(*) FROM information_schema.columns
                 WHERE table_schema = t.table_schema
                 AND table_name = t.table_name) as column_count
            FROM information_schema.tables t
            WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
                AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_schema, t.table_name;
        """)

        tables = []
        for row in cursor.fetchall():
            schema, table_name, description, column_count = row

            # Получаем количество записей (асинхронно для больших таблиц)
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
                record_count = cursor.fetchone()[0]
            except Exception:
                record_count = 'N/A'

            tables.append({
                'schema': schema,
                'table_name': table_name,
                'full_name': f'{schema}.{table_name}',
                'description': description or 'Нет описания',
                'column_count': column_count,
                'record_count': record_count
            })

    return render(request, 'database_viewer/table_list.html', {
        'tables': tables,
        'title': 'СУБД SQL - Список таблиц'
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def table_structure(request):
    """
    AJAX endpoint: Показывает структуру таблицы (поля, типы, ограничения)
    """
    table_name = request.GET.get('table')
    schema = request.GET.get('schema', 'public')

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = %s
            ORDER BY ordinal_position;
        """, [schema, table_name])

        columns = []
        for row in cursor.fetchall():
            col_name, data_type, max_length, is_nullable, default_val, position = row

            # Формируем описание типа
            type_desc = data_type
            if max_length:
                type_desc += f'({max_length})'

            columns.append({
                'name': col_name,
                'type': type_desc,
                'nullable': 'YES' if is_nullable == 'YES' else 'NO',
                'default': default_val or '',
                'position': position
            })

        # Получаем первичные ключи
        cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass
            AND i.indisprimary;
        """, [f'{schema}.{table_name}'])

        primary_keys = [row[0] for row in cursor.fetchall()]

        # Получаем внешние ключи
        cursor.execute("""
            SELECT
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = %s
            AND tc.table_name = %s;
        """, [schema, table_name])

        foreign_keys = []
        for row in cursor.fetchall():
            col_name, foreign_schema, foreign_table, foreign_col = row
            foreign_keys.append({
                'column': col_name,
                'references': f'{foreign_schema}.{foreign_table}({foreign_col})'
            })

    return render(request, 'database_viewer/table_structure.html', {
        'schema': schema,
        'table_name': table_name,
        'columns': columns,
        'primary_keys': primary_keys,
        'foreign_keys': foreign_keys
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def table_data(request):
    """
    AJAX endpoint: Показывает данные таблицы (SELECT * с пагинацией)
    """
    table_name = request.GET.get('table')
    schema = request.GET.get('schema', 'public')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))

    with connection.cursor() as cursor:
        # Получаем имена колонок
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = %s
            ORDER BY ordinal_position;
        """, [schema, table_name])

        columns = [row[0] for row in cursor.fetchall()]

        # Получаем общее количество записей
        cursor.execute(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
        total_count = cursor.fetchone()[0]

        # Получаем данные с пагинацией
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT * FROM "{schema}"."{table_name}"
            ORDER BY 1
            LIMIT %s OFFSET %s;
        ''', [per_page, offset])

        rows = cursor.fetchall()

    # Преобразуем в список словарей
    data = []
    for row in rows:
        row_data = []
        for value in row:
            if value is None:
                row_data.append('<span class="text-muted">NULL</span>')
            elif isinstance(value, str):
                # Обрезаем длинные строки
                if len(value) > 100:
                    row_data.append(f'{value[:100]}...')
                else:
                    row_data.append(value)
            else:
                row_data.append(str(value))
        data.append(row_data)

    # Пагинация
    paginator = Paginator(range(total_count), per_page)
    page_obj = paginator.get_page(page)

    return render(request, 'database_viewer/table_data.html', {
        'schema': schema,
        'table_name': table_name,
        'columns': columns,
        'data': data,
        'page_obj': page_obj,
        'total_count': total_count,
        'per_page': per_page
    })


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def table_relations(request):
    """
    ER диаграмма: Показывает связи между таблицами (как в MS Access)
    """
    with connection.cursor() as cursor:
        # Получаем все внешние ключи
        cursor.execute("""
            SELECT
                tc.table_schema,
                tc.table_name,
                kcu.column_name,
                ccu.table_schema AS foreign_table_schema,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema IS NOT NULL
            WHERE tc.constraint_type = 'FOREIGN KEY'
            ORDER BY tc.table_schema, tc.table_name;
        """)

        relations = []
        for row in cursor.fetchall():
            schema, table, column, foreign_schema, foreign_table, foreign_col, constraint = row

            relations.append({
                'from_table': f'{schema}.{table}',
                'from_column': column,
                'to_table': f'{foreign_schema}.{foreign_table}',
                'to_column': foreign_col,
                'constraint': constraint
            })

        # Получаем список всех таблиц для построения диаграммы
        cursor.execute("""
            SELECT
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name;
        """)

        tables = []
        for row in cursor.fetchall():
            schema, name = row
            tables.append({
                'id': f'{schema}.{name}',
                'name': name,
                'schema': schema
            })

    return render(request, 'database_viewer/table_relations.html', {
        'relations': json.dumps(relations),
        'tables': json.dumps(tables),
        'title': 'СУБД SQL - ER диаграмма'
    })
