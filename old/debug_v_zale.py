#!/usr/bin/env python3
"""
Диагностический скрипт для проверки ошибки на сообщении "в зале"

ЗАПУСК:
    source venv/bin/activate
    python debug_v_zale.py
"""

import asyncio
import sys
import os
import traceback

# Django setup
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from message_handler_service import MessageHandlerService

async def test_v_zale():
    """Тест сценария с сообщением 'в зале'"""

    print("\n" + "="*80)
    print("ТЕСТ: 'течет батарея' -> 'подтекает' -> 'в зале'")
    print("="*80)

    handler = MessageHandlerService()
    session_id = "debug_v_zale_test"
    user_id = "debug_user"

    # Шаг 1: "течет батарея"
    print("\n--- Шаг 1: 'течет батарея' ---")
    try:
        result1 = await handler.handle_incoming_message(
            text="течет батарея",
            user_id=user_id,
            session_id=session_id,
            channel="test"
        )
        print(f"✅ Статус: {result1.get('status')}")
        print(f"✅ Ответ: {result1.get('response', '')[:100]}")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()

    await asyncio.sleep(0.5)

    # Шаг 2: "подтекает"
    print("\n--- Шаг 2: 'подтекает' ---")
    try:
        result2 = await handler.handle_incoming_message(
            text="подтекает",
            user_id=user_id,
            session_id=session_id,
            channel="test"
        )
        print(f"✅ Статус: {result2.get('status')}")
        print(f"✅ Ответ: {result2.get('response', '')[:100]}")
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()

    await asyncio.sleep(0.5)

    # Шаг 3: "в зале" - ЗДЕСЬ ДОЛЖНА БЫТЬ ОШИБКА
    print("\n--- Шаг 3: 'в зале' [КРИТИЧЕСКИЙ ТЕСТ] ---")
    try:
        result3 = await handler.handle_incoming_message(
            text="в зале",
            user_id=user_id,
            session_id=session_id,
            channel="test"
        )
        print(f"✅ Статус: {result3.get('status')}")
        print(f"✅ Ответ: {result3.get('response', '')[:100]}")

        # Проверяем metadata
        if '_metadata' in result3:
            metadata = result3['_metadata']
            print(f"\n📊 METADATA:")
            print(f"  txtPrb: {metadata.get('txtPrb', '(нет)')}")
            print(f"  accumulated_fields: {metadata.get('accumulated_fields', {})}")
            print(f"  established_filters: {metadata.get('established_filters', {})}")
        else:
            print(f"\n⚠️ НЕТ _metadata в результате!")

    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        traceback.print_exc()

    print("\n" + "="*80)
    print("ТЕСТ ЗАВЕРШЁН")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_v_zale())
