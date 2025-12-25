#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест AI агента с исправленным YandexGPT API
"""

import asyncio
from ai_agent_service import AIAgentService

async def test_ai_agent():
    print("🔧 Тест AI агента с YandexGPT")
    print("=" * 50)

    # Инициализация
    ai_agent = AIAgentService()
    print(f"Доступность AI: {ai_agent.is_available}")

    # Тестовый запрос
    test_query = "открылась течь с крыши"
    print(f"\n📍 Запрос: '{test_query}'")
    print("-" * 30)

    result = await ai_agent.search(test_query)

    print(f"Статус: {result.get('status')}")
    print(f"Найдено кандидатов: {len(result.get('candidates', []))}")

    for i, candidate in enumerate(result.get('candidates', []), 1):
        print(f"  {i}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")
        if candidate.get('reason'):
            print(f"     Причина: {candidate.get('reason')}")

    if result.get('error'):
        print(f"Ошибка: {result.get('error')}")

    if result.get('ai_response'):
        print(f"AI ответ: {result.get('ai_response')}")

# Запуск
print("Запуск теста AI агента...")
asyncio.run(test_ai_agent())