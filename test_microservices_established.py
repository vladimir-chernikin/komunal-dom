#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки микросервисов с established_filters
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


async def test_with_established_filters():
    """Тестирует с форматом established_filters"""

    txtPrb = "у пользователя течёт из трубы"

    # Формат established_filters (как в MainAgent)
    established_filters = {
        'category': {'value': 'Водоснабжение', 'confidence': 0.90},
        'incident_type': {'value': 'Инцидент', 'confidence': 0.90}
    }

    print("=" * 80)
    print("ТЕСТИРОВАНИЕ С ESTABLISHED_FILTERS")
    print("=" * 80)
    print(f"txtPrb: '{txtPrb}'")
    print(f"established_filters: {established_filters}")
    print()

    # Тест 1: TagSearchService
    print("=" * 80)
    print("1. TagSearchService с established_filters")
    print("=" * 80)

    try:
        tag_service = TagSearchService()
        tag_result = await tag_service.search(
            message_text=txtPrb,
            filters=established_filters
        )

        print(f"Статус: {tag_result.get('status')}")
        print(f"Найдено кандидатов: {len(tag_result.get('candidates', []))}")

        if tag_result.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(tag_result['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")
        else:
            print("❌ НЕТ КАНДИДАТОВ")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Тест 2: VectorSearchService
    print("=" * 80)
    print("2. VectorSearchService с established_filters")
    print("=" * 80)

    try:
        vector_service = VectorSearchService()
        vector_result = await vector_service.search(
            message_text=txtPrb,
            filters=established_filters
        )

        print(f"Статус: {vector_result.get('status')}")
        print(f"Найдено кандидатов: {len(vector_result.get('candidates', []))}")

        if vector_result.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(vector_result['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")
        else:
            print("❌ НЕТ КАНДИДАТОВ")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Тест 3: SemanticSearchService
    print("=" * 80)
    print("3. SemanticSearchService с established_filters")
    print("=" * 80)

    try:
        semantic_service = SemanticSearchService()
        semantic_result = await semantic_service.search(
            message_text=txtPrb,
            filters=established_filters
        )

        print(f"Статус: {semantic_result.get('status')}")
        print(f"Найдено кандидатов: {len(semantic_result.get('candidates', []))}")

        if semantic_result.get('candidates'):
            print("Кандидаты:")
            for i, candidate in enumerate(semantic_result['candidates'][:5], 1):
                print(f"  {i}. {candidate.get('service_name')} (conf={candidate.get('confidence', 0):.2f})")
        else:
            print("❌ НЕТ КАНДИДАТОВ")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    print()


if __name__ == '__main__':
    asyncio.run(test_with_established_filters())
