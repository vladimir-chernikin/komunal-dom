#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для отладки микросервисов поиска

Проверяет почему TagSearchService, VectorSearchService, SemanticSearchService
возвращают 0 кандидатов при txtPrb="у пользователя течёт из трубы"
"""

import os
import sys
import django
import asyncio

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from tag_search_service import TagSearchService
from vector_search_service import VectorSearchService
from semantic_search_service import SemanticSearchService


async def test_microservices():
    """Тестирует все микросервисы поиска"""

    txtPrb = "у пользователя течёт из трубы"

    print("=" * 80)
    print("ТЕСТИРОВАНИЕ МИКРОСЕРВИСОВ ПОИСКА")
    print("=" * 80)
    print(f"txtPrb: '{txtPrb}'")
    print()

    # Тест 1: TagSearchService
    print("=" * 80)
    print("1. TagSearchService")
    print("=" * 80)

    try:
        tag_service = TagSearchService()
        tag_result = await tag_service.search(
            message_text=txtPrb,
            filters={'category': 'Водоснабжение', 'incident_type': 'Инцидент'}
        )

        print(f"Статус: {tag_result.get('status')}")
        print(f"Найдено кандидатов: {len(tag_result.get('candidates', []))}")

        if tag_result.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(tag_result['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")
        else:
            print("❌ НЕТ КАНДИДАТОВ")

        print(f"Детали: {tag_result.get('details', 'Нет')}")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Тест 2: VectorSearchService
    print("=" * 80)
    print("2. VectorSearchService")
    print("=" * 80)

    try:
        vector_service = VectorSearchService()
        vector_result = await vector_service.search(
            message_text=txtPrb,
            filters={'category': 'Водоснабжение', 'incident_type': 'Инцидент'}
        )

        print(f"Статус: {vector_result.get('status')}")
        print(f"Найдено кандидатов: {len(vector_result.get('candidates', []))}")

        if vector_result.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(vector_result['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")
        else:
            print("❌ НЕТ КАНДИДАТОВ")

        print(f"Детали: {vector_result.get('details', 'Нет')}")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Тест 3: SemanticSearchService
    print("=" * 80)
    print("3. SemanticSearchService")
    print("=" * 80)

    try:
        semantic_service = SemanticSearchService()
        semantic_result = await semantic_service.search(
            message_text=txtPrb,
            filters={'category': 'Водоснабжение', 'incident_type': 'Инцидент'}
        )

        print(f"Статус: {semantic_result.get('status')}")
        print(f"Найдено кандидатов: {len(semantic_result.get('candidates', []))}")

        if semantic_result.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(semantic_result['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")
        else:
            print("❌ НЕТ КАНДИДАТОВ")

        print(f"Детали: {semantic_result.get('details', 'Нет')}")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ БЕЗ ФИЛЬТРОВ")
    print("=" * 80)
    print()

    # Тест без фильтров
    print("=" * 80)
    print("4. TagSearchService БЕЗ ФИЛЬТРОВ")
    print("=" * 80)

    try:
        tag_result_no_filters = await tag_service.search(
            message_text=txtPrb,
            filters=None
        )

        print(f"Статус: {tag_result_no_filters.get('status')}")
        print(f"Найдено кандидатов: {len(tag_result_no_filters.get('candidates', []))}")

        if tag_result_no_filters.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(tag_result_no_filters['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")

    print()


if __name__ == '__main__':
    asyncio.run(test_microservices())
