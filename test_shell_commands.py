#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Команды для тестирования в Django shell
"""

import asyncio
from main_agent import MainAgent

async def test_system():
    # Инициализация MainAgent
    agent = MainAgent()

    # Тестовые запросы
    test_queries = [
        "открылась течь",
        "с крыши",
        "протекает крыша",
        "крыша течет",
        "сломался лифт",
        "нет воды"
    ]

    print("🔧 Тест системы определения услуг")
    print("=" * 50)

    for i, query in enumerate(test_queries, 1):
        print(f"\n📍 Тест {i}: '{query}'")
        print("-" * 30)

        result = await agent.process_service_detection(query)

        print(f"Статус: {result.get('status')}")
        print(f"Сообщение: {result.get('message')}")
        print(f"Найдено кандидатов: {len(result.get('candidates', []))}")

        for j, candidate in enumerate(result.get('candidates', []), 1):
            print(f"  {j}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")

    print("\n🎉 Тест завершен!")

# Запуск
print("Запуск теста...")
asyncio.run(test_system())