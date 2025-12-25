#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Упрощенный тест улучшений по разделению локаций
"""

import asyncio
from main_agent import MainAgent

async def test_location_simple():
    print("🔧 Тест улучшений по разделению локаций")
    print("=" * 50)

    agent = MainAgent()

    # Ключевые тесты
    test_cases = [
        'течь в квартире',
        'протекает крыша',
        'сломался лифт',
        'открылась течь'
    ]

    for test in test_cases:
        print(f"\n📍 Запрос: '{test}'")
        print("-" * 40)

        result = await agent.process_service_detection(test)

        print(f"Статус: {result.get('status')}")
        print(f"Сообщение: {result.get('message', '')[:100]}...")
        print(f"Кандидатов: {len(result.get('candidates', []))}")

        # Проверяем наличие вопроса о локации
        if result.get('needs_clarification'):
            message = result.get('message', '').lower()
            if 'квартире' in message and ('общедомового' in message or 'общее' in message):
                print("✅ Правильный вопрос о разделении локаций")
            elif 'где именно' in message:
                print("✅ Есть уточняющий вопрос о месте")
            else:
                print("⚠️ Вопрос есть, но не о разделении локаций")
        elif result.get('status') == 'SUCCESS':
            print("✅ Услуга определена однозначно")

    print(f"\n🎉 Тест завершен!")

# Запуск
asyncio.run(test_location_simple())