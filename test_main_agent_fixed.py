#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки исправленного MainAgent
"""

import asyncio
import os
import sys
import django

# Установка переменных окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

# Настройка Django
django.setup()

import logging
logging.basicConfig(level=logging.INFO)

async def test_main_agent():
    """Тестируем исправленный MainAgent с различными сообщениями"""

    from main_agent import MainAgent

    # Инициализируем агент
    agent = MainAgent()

    # Тестовые сообщения (проблемные)
    test_messages = [
        "у меня теч",
        "протекает крыша",
        "сломался лифт",
        "нет отопления",
        "свет выключился",
        "нет воды",
        "мусор не убирают",
        "засорилась канализация"
    ]

    print("=== Тестирование исправленного MainAgent ===\n")

    for message in test_messages:
        print(f"Сообщение: '{message}'")
        try:
            result = await agent.process_service_detection(message)

            if result['status'] == 'SUCCESS':
                service_name = result.get('service_name', 'Unknown')
                confidence = result.get('confidence', 0)
                source = result.get('source', 'unknown')
                print(f"✅ Успех: {service_name} (уверенность: {confidence:.2f}, источник: {source})")
            elif result['status'] == 'AMBIGUOUS':
                candidates = result.get('candidates', [])
                message_text = result.get('message', 'Нужны уточнения')
                clarification_type = result.get('clarification_type', 'unknown')
                print(f"❓ Неопределенность ({clarification_type}): {message_text[:100]}...")
                if candidates:
                    print(f"   Кандидаты: {[c.get('service_name', 'Unknown') for c in candidates[:3]]}")
            else:
                print(f"❌ Ошибка: {result.get('message', 'Unknown error')}")

        except Exception as e:
            print(f"❌ Исключение: {e}")
            import traceback
            traceback.print_exc()

        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_main_agent())