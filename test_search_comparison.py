#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сравнительное тестирование поисковых сервисов

ЦЕЛЬ: Определить какой сервис точнее находит услуги
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from tag_search_service import TagSearchService
from semantic_search_service import SemanticSearchService
from vector_search_service import VectorSearchService


async def test_search_services():
    """Сравниваем результаты поиска"""

    print("=" * 100)
    print("СРАВНИТЕЛЬНЫЙ ТЕСТ ПОИСКОВЫХ СЕРВИСОВ")
    print("=" * 100)

    # Инициализация сервисов
    try:
        tag_search = TagSearchService()
        semantic_search = SemanticSearchService()
        vector_search = VectorSearchService()
        print("✅ Все сервисы инициализированы\n")
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        return

    # Тестовые запросы разного типа
    test_queries = [
        {
            'name': 'ТОЧНОЕ СОВПАДЕНИЕ',
            'query': 'течет батарея в зале',
            'expected_category': 'Отопление',
            'expected_object': 'Квартира'
        },
        {
            'name': 'ПРОБЛЕМА С ГАЗОМ (критическая)',
            'query': 'пахнет газом в доме',
            'expected_category': 'Газоснабжение',
            'expected_object': 'Дом'
        },
        {
            'name': 'СИНОНИМЫ',
            'query': 'холодно в квартире',
            'expected_category': 'Отопление',
            'expected_object': 'Квартира'
        },
        {
            'name': 'НЕТОЧНЫЙ ЗАПРОС',
            'query': 'прорыв',
            'expected_category': None,
            'expected_object': None
        },
        {
            'name': 'КОНКРЕТНАЯ ПРОБЛЕМА',
            'query': 'засорился унитаз',
            'expected_category': 'Канализация',
            'expected_object': 'Квартира'
        }
    ]

    for test_case in test_queries:
        print("\n" + "=" * 100)
        print(f"ТЕСТ: {test_case['name']}")
        print(f"ЗАПРОС: '{test_case['query']}'")
        if test_case['expected_category']:
            print(f"ОЖИДАЕТСЯ: category={test_case['expected_category']}, object={test_case['expected_object']}")
        print("=" * 100)

        # Параллельный запуск всех сервисов
        results = await asyncio.gather(
            tag_search.search(test_case['query'], filters={}),
            semantic_search.search(test_case['query'], filters={}),
            vector_search.search(test_case['query'], filters={}),
            return_exceptions=True
        )

        tag_result = results[0] if not isinstance(results[0], Exception) else {'error': str(results[0])}
        semantic_result = results[1] if not isinstance(results[1], Exception) else {'error': str(results[1])}
        vector_result = results[2] if not isinstance(results[2], Exception) else {'error': str(results[2])}

        # Показываем результаты
        services = [
            ('TagSearch', tag_result, '🏷️'),
            ('SemanticSearch', semantic_result, '📚'),
            ('VectorSearch', vector_result, '🔮')
        ]

        for service_name, result, emoji in services:
            print(f"\n{emoji} {service_name}:")
            print("-" * 50)

            if 'error' in result:
                print(f"   ❌ ОШИБКА: {result['error']}")
                continue

            candidates = result.get('candidates', [])
            if not candidates:
                print(f"   ⚠️ Ничего не найдено")
                continue

            print(f"   📊 Найдено: {len(candidates)} кандидатов")

            for i, candidate in enumerate(candidates[:3], 1):
                service_id = candidate.get('service_id')
                service_name = candidate.get('service_name')
                confidence = candidate.get('confidence', 0.0)
                category = candidate.get('category')
                obj = candidate.get('object')

                print(f"   {i}. {service_name} (ID: {service_id})")
                print(f"      Confidence: {confidence:.2f}")
                print(f"      Категория: {category}, Объект: {obj}")

        # Анализ какой сервис точнее
        print("\n" + "-" * 50)
        print("📈 АНАЛИЗ ТОЧНОСТИ:")
        analyze_accuracy(test_case, tag_result, semantic_result, vector_result)


def analyze_accuracy(test_case, tag_result, semantic_result, vector_result):
    """Анализируем точность каждого сервиса"""

    if not test_case['expected_category']:
        print("   ⏭️ Пропуск (нет ожидаемого результата)")
        return

    expected = test_case['expected_category']

    # Проверяем топ-1 результат каждого сервиса
    def get_top_category(result):
        candidates = result.get('candidates', [])
        if candidates:
            return candidates[0].get('category')
        return None

    tag_cat = get_top_category(tag_result)
    semantic_cat = get_top_category(semantic_result)
    vector_cat = get_top_category(vector_result)

    scores = {}

    if tag_cat:
        tag_match = "✅" if tag_cat == expected else "❌"
        scores['TagSearch'] = (tag_cat == expected, tag_cat)
        print(f"   TagSearch: {tag_match} {tag_cat}")

    if semantic_cat:
        semantic_match = "✅" if semantic_cat == expected else "❌"
        scores['SemanticSearch'] = (semantic_cat == expected, semantic_cat)
        print(f"   SemanticSearch: {semantic_match} {semantic_cat}")

    if vector_cat:
        vector_match = "✅" if vector_cat == expected else "❌"
        scores['VectorSearch'] = (vector_cat == expected, vector_cat)
        print(f"   VectorSearch: {vector_match} {vector_cat}")

    # Вывод: кто точнее
    print(f"\n   ОЖИДАЛОСЬ: {expected}")

    # Считаем сколько совпало
    correct = [name for name, (is_correct, cat) in scores.items() if is_correct]
    if correct:
        print(f"   ✅ ТОЧНЫЕ: {', '.join(correct)}")
    else:
        print(f"   ❌ НИКТО НЕ УГАДАЛ!")


if __name__ == "__main__":
    asyncio.run(test_search_services())
