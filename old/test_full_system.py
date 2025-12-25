#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест полной системы определения услуг с контекстом диалога
"""

import asyncio
import logging
import json
from main_agent import MainAgent

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_full_system():
    """Тест полной системы с контекстом диалога"""

    print("🔧 Тест полной системы определения услуг")
    print("=" * 50)

    # Инициализация MainAgent
    agent = MainAgent()

    # Тестовый сценарий 1: "открылась течь"
    print("\n📍 Тест 1: 'открылась течь'")
    print("-" * 30)

    result1 = await agent.process_service_detection("открылась течь")

    print(f"Статус: {result1.get('status')}")
    print(f"Сообщение: {result1.get('message')}")
    print(f"Найдено кандидатов: {len(result1.get('candidates', []))}")

    for i, candidate in enumerate(result1.get('candidates', []), 1):
        print(f"  {i}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")

    # Тестовый сценарий 2: "с крыши" (с имитацией контекста)
    print("\n📍 Тест 2: 'с крыши' (отдельно)")
    print("-" * 30)

    result2 = await agent.process_service_detection("с крыши")

    print(f"Статус: {result2.get('status')}")
    print(f"Сообщение: {result2.get('message')}")
    print(f"Найдено кандидатов: {len(result2.get('candidates', []))}")

    for i, candidate in enumerate(result2.get('candidates', []), 1):
        print(f"  {i}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")

    # Тестовый сценарий 3: Комбинированный запрос
    print("\n📍 Тест 3: 'протекает крыша'")
    print("-" * 30)

    result3 = await agent.process_service_detection("протекает крыша")

    print(f"Статус: {result3.get('status')}")
    print(f"Сообщение: {result3.get('message')}")
    print(f"Найдено кандидатов: {len(result3.get('candidates', []))}")

    for i, candidate in enumerate(result3.get('candidates', []), 1):
        print(f"  {i}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")

    # Тестовый сценарий 4: Нечеткий запрос
    print("\n📍 Тест 4: 'крыша течет'")
    print("-" * 30)

    result4 = await agent.process_service_detection("крыша течет")

    print(f"Статус: {result4.get('status')}")
    print(f"Сообщение: {result4.get('message')}")
    print(f"Найдено кандидатов: {len(result4.get('candidates', []))}")

    for i, candidate in enumerate(result4.get('candidates', []), 1):
        print(f"  {i}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")

    # Тестовый сценарий 5: Запрос без результатов
    print("\n📍 Тест 5: 'какая погода'")
    print("-" * 30)

    result5 = await agent.process_service_detection("какая погода")

    print(f"Статус: {result5.get('status')}")
    print(f"Сообщение: {result5.get('message')}")
    print(f"Нуждается в уточнении: {result5.get('needs_clarification', False)}")

    # Анализ результатов
    print("\n📊 Анализ результатов")
    print("=" * 50)

    success_count = 0
    total_tests = 5

    for i, result in enumerate([result1, result2, result3, result4, result5], 1):
        if result.get('status') in ['SUCCESS', 'AMBIGUOUS']:
            success_count += 1
            status = "✅ OK"
        else:
            status = "❌ FAIL"

        print(f"Тест {i}: {status} ({result.get('status')})")

    print(f"\nИтого: {success_count}/{total_tests} тестов пройдено")

    if success_count >= 4:
        print("🎉 Система работает отлично!")
    elif success_count >= 3:
        print("⚠️ Система работает, но есть проблемы")
    else:
        print("🚨 Система нуждается в доработке")

    return success_count >= 4

if __name__ == "__main__":
    asyncio.run(test_full_system())