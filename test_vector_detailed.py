#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Детальная проверка VectorSearchService - показываем tag_conf и service_conf
"""

import os
import sys
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from vector_search_service import VectorSearchService


async def test_vector_detailed():
    """Показывает детальную разбивку tag_conf и service_conf"""

    txtPrb = "у пользователя течёт из трубы"

    established_filters = {
        'category': {'value': 'Водоснабжение', 'confidence': 0.90},
        'incident_type': {'value': 'Инцидент', 'confidence': 0.90}
    }

    print("=" * 80)
    print("ДЕТАЛЬНАЯ РАЗБИВКА TAG_CONF И SERVICE_CONF")
    print("=" * 80)
    print(f"txtPrb: '{txtPrb}'")
    print()

    vector_service = VectorSearchService()
    result = await vector_service.search(
        message_text=txtPrb,
        filters=established_filters
    )

    candidates = result.get('candidates', [])

    print("КАНДИДАТЫ С РАЗБИВКОЙ:")
    print("-" * 80)

    for i, candidate in enumerate(candidates, 1):
        service_id = candidate.get('service_id')
        name = candidate.get('service_name')
        conf = candidate.get('confidence')
        tag_conf = candidate.get('tag_confidence')
        service_conf = candidate.get('service_confidence')
        source = candidate.get('source')

        # Проверяем на соответствие запросу
        is_relevant = any(word in name.lower() for word in ['прорыв', 'теч', 'труб', 'затопл'])
        status = "✅ РЕЛЕВАНТЕН" if is_relevant else "❌ НЕ РЕЛЕВАНТЕН"

        print(f"{i}. {status}")
        print(f"   Service ID: {service_id}")
        print(f"   Название: {name}")
        print(f"   source: {source}")
        print(f"   tag_confidence: {tag_conf}")
        print(f"   service_confidence: {service_conf}")
        print(f"   final_confidence: {conf}")
        print()


if __name__ == '__main__':
    asyncio.run(test_vector_detailed())
