#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Синтетический тест влияния порогов confidence на результаты поиска

ЦЕЛЬ: Понять как разные пороги (0.90 vs 0.60/0.70/0.80) влияют на:
1. Количество кандидатов
2. Точность поиска
3. False negatives (потеря правильных ответов)
4. False positives (лишние кандидаты)

ДАТА: 2026-02-14
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

import asyncio
import logging
from tag_search_service import TagSearchService
from semantic_search_service import SemanticSearchService
from vector_search_service import VectorSearchService

logging.basicConfig(level=logging.WARNING)  # Отключаем verbose логи

# Синтетические тесты с РАЗНЫМИ CONFIDENCE
TEST_SCENARIOS = [
    {
        'name': 'Сценарий 1: Высокий confidence (0.95)',
        'message': 'прорвало трубу в ванной',
        'filters': {
            'incident_type': {'value': 'Инцидент', 'confidence': 0.95},
            'location_type': {'value': 'Индивидуальное', 'confidence': 0.95},
            'category': {'value': 'Водоснабжение', 'confidence': 0.95}
        },
        'expected_behavior': 'Должен работать с ЛЮБЫМ порогом (0.60-0.95)'
    },
    {
        'name': 'Сценарий 2: Средний confidence (0.75)',
        'message': 'течет в ванной',
        'filters': {
            'incident_type': {'value': 'Инцидент', 'confidence': 0.75},
            'location_type': {'value': 'Индивидуальное', 'confidence': 0.75},
            'category': {'value': 'Водоснабжение', 'confidence': 0.75}
        },
        'expected_behavior': 'Должен работать с MainAgent (0.60/0.70/0.80), но НЕ с 0.90'
    },
    {
        'name': 'Сценарий 3: Низкий confidence (0.65)',
        'message': 'проблема с водой',
        'filters': {
            'category': {'value': 'Водоснабжение', 'confidence': 0.65},
            'location_type': {'value': 'Общедомовое', 'confidence': 0.65}
        },
        'expected_behavior': 'Должен работать только с category=0.60, остальные НЕ сработают'
    },
    {
        'name': 'Сценарий 4: Очень низкий confidence (0.55)',
        'message': 'нужен сантехник',
        'filters': {
            'category': {'value': 'Водоснабжение', 'confidence': 0.55}
        },
        'expected_behavior': 'НЕ должен работать ни с одним порогом'
    },
    {
        'name': 'Сценарий 5: Смешанный confidence (высокий и низкий)',
        'message': 'запах газа в подъезде',
        'filters': {
            'incident_type': {'value': 'Инцидент', 'confidence': 0.95},  # Высокий
            'location_type': {'value': 'Общедомовое', 'confidence': 0.85},  # Средний
            'category': {'value': 'Газоснабжение', 'confidence': 0.65}  # Низкий
        },
        'expected_behavior': 'С 0.90: только incident. С 0.80: incident + location. С 0.60: все'
    }
]


async def test_search_services_with_thresholds():
    """Тестируем поиск с разными уровнями confidence"""

    print("\n" + "=" * 100)
    print("ТЕСТИРОВАНИЕ ВЛИЯНИЯ ПОРОГОВ CONFIDENCE НА ПОИСК")
    print("=" * 100)

    # Инициализация сервисов
    tag_search = TagSearchService()
    semantic_search = SemanticSearchService()
    vector_search = VectorSearchService()

    results = []

    for scenario in TEST_SCENARIOS:
        print(f"\n{'=' * 100}")
        print(f"{scenario['name']}")
        print(f"{'=' * 100}")
        print(f"Сообщение: {scenario['message']}")
        print(f"Фильтры:")
        for key, value in scenario['filters'].items():
            if isinstance(value, dict):
                print(f"  {key}: {value['value']} (confidence={value['confidence']:.2f})")
        print(f"\nОжидаемое поведение: {scenario['expected_behavior']}")

        # Тестируем с ТЕКУЩИМИ фильтрами
        tag_result = await tag_search.search(
            message_text=scenario['message'],
            filters=scenario['filters']
        )

        semantic_result = await semantic_search.search(
            message_text=scenario['message'],
            filters=scenario['filters']
        )

        vector_result = await vector_search.search(
            message_text=scenario['message'],
            filters=scenario['filters']
        )

        # Собираем результаты
        result = {
            'scenario': scenario['name'],
            'filters': scenario['filters'],
            'tag': tag_result.get('candidates', []),
            'semantic': semantic_result.get('candidates', []),
            'vector': vector_result.get('candidates', [])
        }

        results.append(result)

        # Показываем результаты
        print(f"\n📊 РЕЗУЛЬТАТЫ ПОИСКА:")
        print(f"{'Сервис':<20} {'Найдено':<10} {'Топ-3 кандидата'}")
        print("-" * 100)

        # TagSearch
        tag_candidates = result['tag']
        print(f"{'TagSearch':<20} {len(tag_candidates):<10} ", end="")
        for i, c in enumerate(tag_candidates[:3], 1):
            name = c.get('service_name', 'Unknown')[:30]
            conf = c.get('confidence', 0)
            print(f"\n  {i}. {name} (conf={conf:.2f})", end="")

        print("\n")

        # SemanticSearch
        semantic_candidates = result['semantic']
        print(f"{'SemanticSearch':<20} {len(semantic_candidates):<10} ", end="")
        for i, c in enumerate(semantic_candidates[:3], 1):
            name = c.get('service_name', 'Unknown')[:30]
            conf = c.get('confidence', 0)
            print(f"\n  {i}. {name} (conf={conf:.2f})", end="")

        print("\n")

        # VectorSearch
        vector_candidates = result['vector']
        print(f"{'VectorSearch':<20} {len(vector_candidates):<10} ", end="")
        for i, c in enumerate(vector_candidates[:3], 1):
            name = c.get('service_name', 'Unknown')[:30]
            conf = c.get('confidence', 0)
            print(f"\n  {i}. {name} (conf={conf:.2f})", end="")

        print("\n")

        # Анализ
        print(f"\n💡 АНАЛИЗ:")
        analyze_scenario_result(scenario, result)

    # Итоговый отчет
    print_final_report(results)


def analyze_scenario_result(scenario: dict, result: dict):
    """Анализирует результат одного сценария"""

    filters = scenario['filters']

    # Определяем минимальный confidence среди фильтров
    min_confidence = min(
        f['confidence'] for f in filters.values() if isinstance(f, dict)
    )

    # Смотрим какие сервисы что-то нашли
    tag_count = len(result['tag'])
    semantic_count = len(result['semantic'])
    vector_count = len(result['vector'])

    print(f"  Минимальный confidence фильтров: {min_confidence:.2f}")

    # Проверяем работу TagSearch и SemanticSearch (у них порог 0.90)
    if min_confidence >= 0.90:
        print(f"  ✅ Confidence >= 0.90: TagSearch/SemanticSearch ДОЛЖНЫ использовать фильтры")
    elif min_confidence >= 0.80:
        print(f"  ⚠️ 0.80 <= Confidence < 0.90:")
        print(f"     - MainAgent(location) ПРИМЕНЕТ фильтр (0.80)")
        print(f"     - TagSearch/SemanticSearch ИГНОРИРУЮТ фильтры (нужно 0.90)")
    elif min_confidence >= 0.70:
        print(f"  ⚠️ 0.70 <= Confidence < 0.80:")
        print(f"     - MainAgent(incident) ПРИМЕНЕТ фильтр (0.70)")
        print(f"     - TagSearch/SemanticSearch ИГНОРИРУЮТ фильтры (нужно 0.90)")
    elif min_confidence >= 0.60:
        print(f"  ⚠️ 0.60 <= Confidence < 0.70:")
        print(f"     - MainAgent(category) ПРИМЕНЕТ фильтр (0.60)")
        print(f"     - TagSearch/SemanticSearch ИГНОРИРУЮТ фильтры (нужно 0.90)")
    else:
        print(f"  ❌ Confidence < 0.60:")
        print(f"     - MainAgent ИГНОРИРУЕТ все фильтры")
        print(f"     - TagSearch/SemanticSearch ИГНОРИРУЮТ фильтры")

    # Если никто ничего не нашел
    if tag_count == 0 and semantic_count == 0 and vector_count == 0:
        print(f"  ❌ НИКТО не нашел кандидатов!")
    else:
        print(f"  ✅ Кандидаты найдены:")
        print(f"     - TagSearch: {tag_count}")
        print(f"     - SemanticSearch: {semantic_count}")
        print(f"     - VectorSearch: {vector_count}")


def print_final_report(results: list):
    """Печатает итоговый отчет"""

    print("\n" + "=" * 100)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 100)

    print("\n📊 СВОДНАЯ ТАБЛИЦА:")
    print(f"{'Сценарий':<30} {'TagSearch':<15} {'SemanticSearch':<20} {'VectorSearch':<15}")
    print("-" * 100)

    for result in results:
        scenario_name = result['scenario']
        tag_count = len(result['tag'])
        semantic_count = len(result['semantic'])
        vector_count = len(result['vector'])

        print(f"{scenario_name:<30} {tag_count:<15} {semantic_count:<20} {vector_count:<15}")

    print("\n" + "=" * 100)
    print("💡 ВЫВОДЫ:")
    print("=" * 100)

    print("""
1. ЕСЛИ TagSearch/SemanticSearch находят МЕНЬШЕ чем VectorSearch:
   → Порог 0.90 СЛИШКОМ СТРОГ
   → FilterDetectionService возвращает confidence < 0.90
   → НУЖНО СНИЗИТЬ порог в TagSearch/SemanticSearch до 0.70 или 0.80

2. ЕСЛИ TagSearch/SemanticSearch находят СТОЛЬКО ЖЕ сколько VectorSearch:
   → Порог 0.90 НОРМАЛЬНЫЙ
   → FilterDetectionService возвращает confidence >= 0.90
   → МОЖНО ОСТАВИТЬ как есть

3. ЕСЛИ VectorSearch находит МЕНЬШЕ чем TagSearch/SemanticSearch:
   → VectorSearch (порог 0.70) ЛИБЕРАЛЬНЕЕ
   → НУЖНО ПОВЫСИТЬ порог VectorSearch до 0.80 или 0.90

4. РЕКОМЕНДАЦИЯ:
   → Смотреть на Сценарий 2 и 3 (confidence 0.65-0.75)
   → Если там TagSearch/SemanticSearch ничего не находят - НУЖНО СНИЖАТЬ ПОРОГ
   → Если находят - текущие порги ОК
    """)

    print("\n" + "=" * 100)
    print("🔬 ДЛЯ ДАЛЬНЕЙШЕГО АНАЛИЗА:")
    print("=" * 100)
    print("""
1. Посмотреть на Сценарий 2 (confidence 0.75):
   - Если TagSearch/SemanticSearch = 0: Порог 0.90 слишком строгий
   - Если TagSearch/SemanticSearch > 0: Все ок

2. Посмотреть на Сценарий 5 (смешанный confidence):
   - Показать как разные пороги влияют на разные фильтры
   - Выявить какой порог оптимальный

3. Сравнить с реальными данными из FilterDetectionService
   - Какое распределение confidence в реальных диалогах?
   - Сколько процентов >= 0.90?
    """)


if __name__ == '__main__':
    asyncio.run(test_search_services_with_thresholds())
