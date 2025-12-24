#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки MainAgent
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
    """Тестируем MainAgent с различными сообщениями"""

    from main_agent import MainAgent

    # Инициализируем агент
    agent = MainAgent()

    # Тестовые сообщения
    test_messages = [
        "у меня теч",
        "сломался лифт",
        "нет отопления",
        "протекает крыша",
        "засорилась канализация",
        "свет выключился",
        "нет воды",
        "мусор не убирают"
    ]

    print("=== Тестирование MainAgent ===\n")

    for message in test_messages:
        print(f"Сообщение: '{message}'")
        try:
            result = await agent.process_service_detection(message)

            if result['status'] == 'SUCCESS':
                service_name = result.get('service_name', 'Unknown')
                confidence = result.get('confidence', 0)
                print(f"✅ Успех: {service_name} (уверенность: {confidence:.2f})")
            elif result['status'] == 'AMBIGUOUS':
                candidates = result.get('candidates', [])
                message_text = result.get('message', 'Нужны уточнения')
                print(f"❓ Неопределенность: {message_text}")
                if candidates:
                    print(f"   Кандидаты: {[c.get('service_name', 'Unknown') for c in candidates[:3]]}")
            else:
                print(f"❌ Ошибка: {result.get('message', 'Unknown error')}")

        except Exception as e:
            print(f"❌ Исключение: {e}")

        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_main_agent())