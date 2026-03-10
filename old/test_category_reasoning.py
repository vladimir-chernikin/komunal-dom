#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование обновленного промпта filter-category с цепочкой рассуждений
"""

import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from filter_detection_service import FilterDetectionService
from ai_agent_service import AIAgentService


async def test_category_detection():
    """Тестирование определения категории"""

    # Инициализируем AIAgentService
    ai_agent = AIAgentService(provider='gigachat')
    service = FilterDetectionService(ai_agent_service=ai_agent)

    test_cases = [
        {
            'txt_prb': 'у меня течет труба в ванной',
            'expected': 'Водоснабжение'
        },
        {
            'txt_prb': 'прорвало канализацию, засор в унитазе',
            'expected': 'Канализация'
        },
        {
            'txt_prb': 'батарея не греет, в квартире холодно',
            'expected': 'Отопление'
        },
        {
            'txt_prb': 'нет света, розетка не работает',
            'expected': 'Электричество'
        },
        {
            'txt_prb': 'лифт застрял на 5 этаже',
            'expected': 'Лифты'
        },
        {
            'txt_prb': 'плохая вентиляция, запах на кухне',
            'expected': 'Вентиляция'
        },
        {
            'txt_prb': 'трещина на стене, потолок протекает',
            'expected': 'Конструктив'
        },
        {
            'txt_prb': 'мусор не вывозят, грязь во дворе',
            'expected': 'Санитария'
        },
        {
            'txt_prb': 'как узнать задолженность по квартплате',
            'expected': 'Информационные запросы'
        },
        {
            'txt_prb': 'дерево упало на дорожку',
            'expected': 'Озеленение'
        }
    ]

    print('=' * 80)
    print('ТЕСТИРОВАНИЕ ОПРЕДЕЛЕНИЯ КАТЕГОРИИ С ЦЕПОЧКОЙ РАССУЖДЕНИЙ')
    print('=' * 80)

    for i, test in enumerate(test_cases, 1):
        print(f'\n--- ТЕСТ {i}: {test["txt_prb"]} ---')
        print(f'Ожидается: {test["expected"]}')

        result = await service.detect_filters(test['txt_prb'], session_id=f'test_{i}')

        # Извлекаем данные о категории
        category_data = result.get('details', {}).get('category') if result.get('details') else None
        category = category_data.get('value') if category_data else None
        confidence = category_data.get('confidence') if category_data else None
        reasoning = category_data.get('reasoning', '') if category_data else ''

        print(f'Результат: {category} (confidence={confidence})')

        if category == test['expected']:
            print('✓ УСПЕХ')
        else:
            print('✗ ОШИБКА')

        if reasoning:
            # Показываем последнюю часть рассуждения
            parts = reasoning.split('|')
            if len(parts) > 3:
                print('Рассуждение:')
                for part in parts[-4:]:
                    print(f'  {part.strip()}')

    print('\n' + '=' * 80)


if __name__ == '__main__':
    asyncio.run(test_category_detection())
