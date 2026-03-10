#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Проверка объединения результатов в MainAgent
"""

import os
import sys
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from main_agent import MainAgent


async def test_main_agent_merge():
    """Проверяет как MainAgent объединяет результаты"""

    txtPrb = "у пользователя течёт из трубы"

    print("=" * 80)
    print("ПРОВЕРКА ОБЪЕДИНЕНИЯ В MAINAGENT")
    print("=" * 80)
    print(f"txtPrb: '{txtPrb}'")
    print()

    main_agent = MainAgent()

    # Результаты от каждого микросервиса
    print("=" * 80)
    print("1. РЕЗУЛЬТАТЫ ОТДЕЛЬНЫХ МИКРОСЕРВИСОВ")
    print("=" * 80)

    # TagSearchService
    from tag_search_service import TagSearchService
    tag_service = TagSearchService()
    tag_result = await tag_service.search(
        message_text=txtPrb,
        filters={'category': {'value': 'Водоснабжение', 'confidence': 0.9}}
    )

    print(f"\nTagSearchService:")
    print(f"  Найдено: {len(tag_result.get('candidates', []))} кандидатов")
    for c in tag_result.get('candidates', []):
        print(f"    - {c.get('service_name')} (conf={c.get('confidence', 0):.3f})")

    # VectorSearchService
    from vector_search_service import VectorSearchService
    vector_service = VectorSearchService()
    vector_result = await vector_service.search(
        message_text=txtPrb,
        filters={'category': {'value': 'Водоснабжение', 'confidence': 0.9}}
    )

    print(f"\nVectorSearchService:")
    print(f"  Найдено: {len(vector_result.get('candidates', []))} кандидатов")
    for c in vector_result.get('candidates', []):
        print(f"    - {c.get('service_name')} (conf={c.get('confidence', 0):.3f})")

    # SemanticSearchService
    from semantic_search_service import SemanticSearchService
    semantic_service = SemanticSearchService()
    semantic_result = await semantic_service.search(
        message_text=txtPrb,
        filters={'category': {'value': 'Водоснабжение', 'confidence': 0.9}}
    )

    print(f"\nSemanticSearchService:")
    print(f"  Найдено: {len(semantic_result.get('candidates', []))} кандидатов")
    for c in semantic_result.get('candidates', []):
        print(f"    - {c.get('service_name')} (conf={c.get('confidence', 0):.3f})")

    print()
    print("=" * 80)
    print("2. ОБЪЕДИНЕНИЕ В MAINAGENT")
    print("=" * 80)

    # Симулируем объединение как в MainAgent
    search_results = {
        'tag_search': tag_result,
        'vector_search': vector_result,
        'semantic_search': semantic_result
    }

    # Подготавливаем кандидатов для объединения
    all_candidates = []

    for service_name, result in search_results.items():
        for candidate in result.get('candidates', []):
            candidate['source'] = service_name
            all_candidates.append(candidate)

    # Вызываем метод объединения MainAgent
    merged = main_agent._merge_candidates(all_candidates)

    print(f"\nОбъединено: {len(merged)} кандидатов")
    print()
    print("ТОП-10 ПОСЛЕ ОБЪЕДИНЕНИЯ:")
    print("-" * 80)

    for i, candidate in enumerate(merged[:10], 1):
        service_id = candidate.get('service_id')
        name = candidate.get('service_name')
        conf = candidate.get('confidence', 0)
        sources = candidate.get('sources', [])

        # Проверяем на соответствие запросу
        is_relevant = any(word in name.lower() for word in ['прорыв', 'теч', 'труб', 'затопл'])
        status = "✅ РЕЛЕВАНТЕН" if is_relevant else "❌ НЕ РЕЛЕВАНТЕН"

        print(f"{i}. {status}")
        print(f"   Service ID: {service_id}")
        print(f"   Название: {name}")
        print(f"   Final Confidence: {conf:.3f}")
        print(f"   Sources: {', '.join(sources)}")
        print()


if __name__ == '__main__':
    asyncio.run(test_main_agent_merge())
