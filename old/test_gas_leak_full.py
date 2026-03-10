#!/usr/bin/env python3
"""
Полный тест сценария 'пахнет газом'

ПРОВЕРЯЕТ:
1. Правильность вопроса после "пахнет газом"
2. Правильность вопроса после ответа на локацию
3. Создание заявки после известной локации
4. Наличие txtPrb в metadata
"""

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

async def test_gas_leak():
    """Тест сценария 'пахнет газом'"""

    print("\n" + "="*80)
    print("ТЕСТ СЦЕНАРИЯ: 'пахнет газом'")
    print("="*80)

    # Инициализируем MainAgent и MessageHandlerService
    main_agent = MainAgent()
    handler = MessageHandlerService(main_agent=main_agent)

    # ИСПРАВЛЕНО (2026-02-17): Используем уникальный session_id с timestamp
    # чтобы избежать конфликтов со старой историей в БД
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    session_id = f"test_gas_leak_full_{timestamp}"
    user_id = "test_user"

    print(f"[INFO] Используется уникальный session_id: {session_id}")

    # Шаг 1: "пахнет газом"
    print("\n--- Шаг 1: 'пахнет газом' ---")
    result1 = await handler.handle_incoming_message(
        text="пахнет газом",
        user_id=user_id,
        session_id=session_id,
        channel="test"
    )

    print(f"✅ Статус: {result1.get('status')}")
    print(f"✅ Ответ: {result1.get('response', '')}")

    # Проверяем metadata
    if '_metadata' in result1:
        metadata1 = result1['_metadata']
        print(f"✅ Есть metadata")
        print(f"  txtPrb: {metadata1.get('txtPrb', '(нет)')}")
        print(f"  accumulated_fields: {metadata1.get('accumulated_fields', {})}")
        print(f"  established_filters: {metadata1.get('established_filters', {})}")
    else:
        print(f"❌ НЕТ metadata в результате!")

    await asyncio.sleep(0.5)

    # Шаг 2: "на кухне"
    print("\n--- Шаг 2: 'на кухне' ---")
    result2 = await handler.handle_incoming_message(
        text="на кухне",
        user_id=user_id,
        session_id=session_id,
        channel="test"
    )

    print(f"✅ Статус: {result2.get('status')}")
    print(f"✅ Ответ: {result2.get('response', '')}")

    # Проверяем metadata
    if '_metadata' in result2:
        metadata2 = result2['_metadata']
        print(f"✅ Есть metadata")
        print(f"  txtPrb: {metadata2.get('txtPrb', '(нет)')}")
        print(f"  accumulated_fields: {metadata2.get('accumulated_fields', {})}")

        # Проверка: txtPrb должен содержать "кухня"
        if 'кухня' in metadata2.get('txtPrb', '').lower():
            print(f"✅ txtPrb содержит 'кухня'")
        else:
            print(f"❌ txtPrb НЕ содержит 'кухня'")
    else:
        print(f"❌ НЕТ metadata в результате!")

    # Анализ результатов
    print("\n" + "="*80)
    print("АНАЛИЗ РЕЗУЛЬТАТОВ:")
    print("="*80)

    # Проверка 1: Первый вопрос
    msg1 = result1.get('response', '').lower()
    if 'запах' in msg1 and ('откуда' in msg1 or 'где' in msg1 or 'как' in msg1):
        print("✅ Шаг 1: Бот задал вопрос про запах")
    else:
        print(f"❌ Шаг 1: Вопрос не соответствует ожиданию. Ответ: {msg1}")

    # Проверка 2: Создание заявки
    msg2 = result2.get('response', '').lower()
    if 'заявк' in msg2 and result2.get('status') == 'SUCCESS':
        print("✅ Шаг 2: После 'на кухне' создана заявка")
    else:
        print(f"❌ Шаг 2: Заявка НЕ создана. Ответ: {msg2}, Статус: {result2.get('status')}")

    # Проверка 3: service_id
    if result2.get('service_detected') == 51:  # Запах газа
        print("✅ Шаг 3: Правильно определена услуга (service_id=51)")
    else:
        print(f"⚠️ Шаг 3: service_id = {result2.get('service_detected')}")

    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(test_gas_leak())
