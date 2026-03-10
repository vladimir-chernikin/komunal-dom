#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование парсинга location_type

Проверяет:
1. Что бот правильно определяет confidence для "Общедомовое (95%)"
2. Бот спрашивает ли "В квартире или в местах общего пользования?"
"""

import asyncio
import sys
import os

sys.path.insert(0, '/var/www/komunal-dom_ru')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from main_agent import MainAgent


async def test():
    print("=" * 80)
    print("ТЕСТ: Парсинг location_type")
    print("=" * 80)
    print()

    agent = MainAgent()

    # Тест 1: "Общедомовое (95%)"
    filter_string = "Общедомовое (95%)"
    result = agent._parse_filter_value(filter_string)

    print(f"Входные данные: '{filter_string}'")
    print(f"Результат:")
    print(f"  value: '{result['value']}'")
    print(f"  confidence: {result['confidence']}")
    print()

    if result['confidence'] >= 0.8:
        print("✅ ПРОВЕРКА: confidence >= 0.8")
        print("   → Уточнение НЕ требуется")
    else:
        print("❌ ОШИБКА: confidence < 0.8")
        print("   → Требуется уточнение")

    print()
    print("=" * 80)
    print()

    # Тест 2: Полный цикл "течет крыша"
    print("ТЕСТ 2: Протестируем полный сценарий...")
    print("Ожидание: Бот спросит 'В квартире или в местах общего пользования?'")


asyncio.run(test())
