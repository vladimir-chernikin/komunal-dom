#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест сценария "пахнет газом"

Проверка исправленной логики передачи accumulated_fields
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/komunal-dom_ru')

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from message_handler_service import MessageHandlerService

async def test_gas_leak():
    """Тест сценария 'пахнет газом'"""

    print("=" * 80)
    print("ТЕСТ: Сценарий 'пахнет газом'")
    print("=" * 80)

    # Инициализируем сервис
    handler = MessageHandlerService()

    # Генерируем уникальный session_id
    import uuid
    session_id = f"test_gas_{uuid.uuid4().hex[:8]}"

    print(f"\n[+] Session ID: {session_id}")

    # Первое сообщение: "пахнет газом"
    print("\n" + "=" * 80)
    print("Шаг 1: Пользователь пишет 'пахнет газом'")
    print("=" * 80)

    result1 = await handler.handle_incoming_message(
        text="пахнет газом",
        user_id="test_user_123",
        channel="web",
        session_id=session_id,
        message_id=f"test_msg_1_{uuid.uuid4().hex[:8]}"
    )

    print(f"\n[!] Ответ бота: {result1.get('response', 'NO RESPONSE')}")
    print(f"[!] Статус: {result1.get('status', 'NO STATUS')}")

    # Проверяем, что НЕ используется fallback вопрос
    response = result1.get('response', '')
    if 'Уточните, пожалуйста, детали проблемы' in response:
        print("\n❌ ERROR: Бот ИСПОЛЬЗУЕТ fallback вопрос!")
        print("❌ Исправления НЕ работают!")
        return False
    elif response and len(response) > 10:
        print("\n✅ SUCCESS: Бот задает КОНКРЕТНЫЙ вопрос!")
        print(f"✅ Вопрос: {response}")
        return True
    else:
        print("\n⚠️ WARNING: Неопределенный ответ")
        return None

if __name__ == "__main__":
    result = asyncio.run(test_gas_leak())

    print("\n" + "=" * 80)
    if result:
        print("ИТОГ: ✅ ТЕСТ ПРОЙДЕН - Исправления работают!")
    elif result is False:
        print("ИТОГ: ❌ ТЕСТ НЕ ПРОЙДЕН - Исправления НЕ работают!")
    else:
        print("ИТОГ: ⚠️ ТЕСТ НЕОПРЕДЕЛЕН")
    print("=" * 80)
