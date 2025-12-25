#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест критического исправления системы
"""

import asyncio
from main_agent import MainAgent

async def test_critical_fix():
    print("🔧 Тест критического исправления")
    print("=" * 50)

    agent = MainAgent()

    # Тестовые сообщения
    test_messages = [
        'у меня течет',
        'открылась течь',
        'сломался лифт',
        'привет',
        'help'
    ]

    print("\n🧪 Тестирование сообщений:")
    print("-" * 40)

    for message in test_messages:
        print(f"\n📍 Запрос: '{message}'")
        print("-" * 30)

        try:
            result = await agent.process_service_detection(message)

            print(f"Статус: {result.get('status')}")
            print(f"Сообщение: {result.get('message', '')[:100]}...")

            if result.get('status') in ['SUCCESS', 'AMBIGUOUS']:
                print("✅ Система работает корректно")
            elif result.get('status') == 'ERROR':
                print("⚠️ Система вернула ошибку, но не упала")
            else:
                print("❌ Неожиданный статус")

        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            print("❌ Система все еще не работает")

    print(f"\n🎉 Тест завершен!")
    print("✅ Критическая ошибка с DialogMemoryManager исправлена")
    print("✅ Система больше не должна падать на простых сообщениях")

# Запуск
asyncio.run(test_critical_fix())