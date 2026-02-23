#!/usr/bin/env python3
"""Простой тест сценария 'течет батарея'"""

import asyncio
import sys
import os

# Django setup
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from message_handler_service import MessageHandlerService
from main_agent import MainAgent

async def main():
    print("="*80)
    print("ПРЯМОЙ ТЕСТ: 'течет батарея'")
    print("="*80)

    # Создание MainAgent
    agent = MainAgent()

    session_id = "test_battery_simple"
    user_id = "test_user"

    # Шаг 1
    print("\n--- Шаг 1: 'течет батарея' ---")
    result1 = await agent.process_service_detection(
        message_text="течет батарея",
        user_id=user_id,
        session_id=session_id,
        channel="test"
    )

    print(f"Статус: {result1.get('status')}")
    print(f"Сообщение: {result1.get('message', '')[0:100]}...")
    print(f"Кандидатов: {len(result1.get('candidates', []))}")

    # Шаг 2
    print("\n--- Шаг 2: 'в зале' ---")
    result2 = await agent.process_service_detection(
        message_text="в зале",
        user_id=user_id,
        session_id=session_id,
        channel="test"
    )

    print(f"Статус: {result2.get('status')}")
    print(f"Сообщение: {result2.get('message', '')[0:100]}...")

    # Проверка
    print("\n" + "="*80)
    print("РЕЗУЛЬТАТ:")
    print("="*80)

    msg1 = result1.get('message', '').lower()
    msg2 = result2.get('message', '').lower()

    if "зал" in msg1 or "комнат" in msg1 or "где" in msg1:
        print("✅ Шаг 1: Бот задал вопрос о локации")
    else:
        print(f"❌ Шаг 1: Бот НЕ задал вопрос. Сообщение: {msg1}")

    if "заявк" in msg2 and result2.get('status') == 'SUCCESS':
        print("✅ Шаг 2: Создана заявка БЕЗ лишнего вопроса")
    elif "подробн" in msg2 or "как именно" in msg2:
        print("❌ Шаг 2: Бот задал ЛИШНИЙ вопрос 'Опишите подробнее...'")
    else:
        print(f"⚠️ Шаг 2: Неожиданное сообщение: {msg2}")

if __name__ == "__main__":
    asyncio.run(main())
