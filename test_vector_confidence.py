#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Проверка confidence scores для VectorSearchService
"""

import os
import sys
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from vector_search_service import VectorSearchService


async def test_vector_confidence():
    """Проверяет детальные confidence scores"""

    txtPrb = "у пользователя течёт из трубы"

    established_filters = {
        'category': {'value': 'Водоснабжение', 'confidence': 0.90},
        'incident_type': {'value': 'Инцидент', 'confidence': 0.90}
    }

    print("=" * 80)
    print("ДЕТАЛЬНАЯ ПРОВЕРКА VECTORSEARCHSERVICE")
    print("=" * 80)
    print(f"txtPrb: '{txtPrb}'")
    print()

    vector_service = VectorSearchService()
    vector_result = await vector_service.search(
        message_text=txtPrb,
        filters=established_filters
    )

    print(f"Статус: {vector_result.get('status')}")
    print(f"Всего найдено: {len(vector_result.get('candidates', []))}")
    print()

    # Сортируем по confidence
    candidates = sorted(
        vector_result.get('candidates', []),
        key=lambda x: x.get('confidence', 0),
        reverse=True
    )

    print("Кандидаты ПОРЯДКЕ УБЫВАНИЯ CONFIDENCE:")
    print("-" * 80)

    for i, candidate in enumerate(candidates, 1):
        conf = candidate.get('confidence', 0)
        name = candidate.get('service_name', 'Unknown')
        service_id = candidate.get('service_id', 0)

        # Проверяем на соответствие запросу
        is_relevant = any(word in name.lower() for word in ['прорыв', 'теч', 'труб', 'затопл'])
        status = "✅ РЕЛЕВАНТЕН" if is_relevant else "❌ НЕ РЕЛЕВАНТЕН"

        print(f"{i}. {status}")
        print(f"   Service ID: {service_id}")
        print(f"   Название: {name}")
        print(f"   Confidence: {conf:.4f} ({conf*100:.1f}%)")
        print()


if __name__ == '__main__':
    asyncio.run(test_vector_confidence())
