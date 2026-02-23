#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест сценария "Прорыв трубы"

Проверяет создаётся ли заявка через веб-чат
"""

import os
import django
import sys
import asyncio

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from message_handler_service import MessageHandlerService
from main_agent import MainAgent


async def test_leak_scenario():
    """Тестируем сценарий: прорыв трубы на чердаке"""
    print("=" * 60)
    print("ТЕСТ: Прорыв трубы на чердаке")
    print("=" * 60)

    # Инициализация сервисов
    main_agent = MainAgent()
    message_handler = MessageHandlerService(main_agent=main_agent)

    # Тестовый пользователь (tstUser ID=3)
    user_id = "3"
    session_id = f"test_leak_{user_id}"

    # Сценарий диалога
    messages = [
        "привет",
        "у меня прорвало трубу",
        "на чердаке"
    ]

    for i, message in enumerate(messages, 1):
        print(f"\n{'='*60}")
        print(f"Шаг {i}: Житель пишет: '{message}'")
        print(f"{'='*60}")

        try:
            result = await message_handler.handle_incoming_message(
                text=message,
                user_id=user_id,
                channel='web',
                session_id=session_id,
                django_user_id=3
            )

            print(f"\n📥 Результат:")
            print(f"  Статус: {result.get('status', 'UNKNOWN')}")
            print(f"  Ответ бота: {result.get('response', '')[:200]}")

            if result.get('status') == 'SUCCESS':
                print(f"\n✅ Услуга определена:")
                print(f"    ID: {result.get('service_id')}")
                print(f"    Название: {result.get('service_name')}")
                print(f"    Confidence: {result.get('confidence', 0):.2%}")
            else:
                print(f"\n❌ Услуга НЕ определена (уточняющий вопрос)")

        except Exception as e:
            print(f"\n❌ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("ТЕСТ ЗАВЕРШЁН")
    print("=" * 60)

    # Проверка - создалась ли заявка
    print("\n🔍 Проверка заявки в БД...")
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                service_name,
                street_name,
                description,
                status,
                created_at
            FROM bot_service_requests
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 5
        """, [user_id])

        requests = cursor.fetchall()

        if requests:
            print(f"\n✅ НАЙДЕНО {len(requests)} заявок пользователя tstUser:")
            for req in requests:
                print(f"    ID={req[0]} | {req[1]} | {req[2]} | Статус={req[4]}")
        else:
            print("\n❌ Заявок НЕ найдено!")

    print("\n" + "=" * 60)


if __name__ == '__main__':
    asyncio.run(test_leak_scenario())
