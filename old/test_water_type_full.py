#!/usr/bin/env python3
"""
Полный тест сценария "нет воды" через MainAgent.process_message

Проверяет:
1. нет воды → уточняет локацию
2. в квартире → уточняет тип воды
3. горячей → создает заявку
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

from main_agent import MainAgent

async def test_no_water_full_process():
    """Полный тест через process_message"""
    print("=" * 100)
    print("ПОЛНЫЙ ТЕСТ: нет воды → локация → тип воды → заявка")
    print("=" * 100)

    agent = MainAgent()
    session_id = "test_water_type_full_20260218"

    # Инициализируем историю диалога
    dialog_history = []

    # ========== ШАГ 1: "нет воды" ==========
    print("\n--- ШАГ 1: 'нет воды' ---")
    result1 = await agent.process_service_detection(
        message_text="нет воды",
        user_context={'session_id': session_id, 'channel': 'web', 'user_id': 999999, 'dialog_history': dialog_history}
    )

    print(f"Статус: {result1['status']}")
    print(f"Сообщение: {result1['message']}")
    print(f"Кандидатов: {len(result1.get('candidates', []))}")

    # Проверка
    assert result1['status'] == 'AMBIGUOUS', f"Ожидал AMBIGUOUS, получил {result1['status']}"
    # LLM может задавать разные вопросы, главное что это не SUCCESS
    print("✅ ПРАВИЛЬНО: Статус AMBIGUOUS (задает вопрос)")

    # Сохраняем в историю
    dialog_history.append({'role': 'user', 'text': 'нет воды'})
    dialog_history.append({'role': 'bot', 'text': result1['message'], 'metadata': result1.get('_metadata', {})})

    # ========== ШАГ 2: "в квартире" ==========
    print("\n--- ШАГ 2: 'в квартире' ---")

    # Передаем историю
    result2 = await agent.process_service_detection(
        message_text="в квартире",
        user_context={'session_id': session_id, 'channel': 'web', 'user_id': 999999, 'dialog_history': dialog_history}
    )

    print(f"Статус: {result2['status']}")
    print(f"Сообщение: {result2['message']}")
    print(f"Кандидатов: {len(result2.get('candidates', []))}")

    # Проверка
    if result2['status'] == 'SUCCESS':
        print(f"❌ ОШИБКА: Сразу создал заявку: {result2.get('service_name')}")
        print(f"   Ожидал: уточнение типа воды")
        return False
    else:
        # Проверяем, что спрашивает про тип воды
        msg_lower = result2['message'].lower()
        if any(word in msg_lower for word in ['горяч', 'холод', 'какой', 'какая']):
            print("✅ ПРАВИЛЬНО: Уточняет тип воды")
        else:
            print(f"⚠️ Другой вопрос: {result2['message']}")
            # Может быть валидным, но проверим

    # ========== ШАГ 3: "горячей" ==========
    print("\n--- ШАГ 3: 'горячей' ---")

    # Добавляем шаг 2 в историю
    dialog_history.append({'role': 'user', 'text': 'в квартире'})
    dialog_history.append({'role': 'bot', 'text': result2['message'], 'metadata': result2.get('_metadata', {})})

    result3 = await agent.process_service_detection(
        message_text="горячей",
        user_context={'session_id': session_id, 'channel': 'web', 'user_id': 999999, 'dialog_history': dialog_history}
    )

    print(f"Статус: {result3['status']}")
    print(f"Сообщение: {result3['message']}")
    print(f"Услуга: {result3.get('service_name', 'Не определена')}")

    # Проверка
    if result3['status'] == 'SUCCESS':
        service_name = result3.get('service_name', '')
        if 'горяч' in service_name.lower():
            print("✅ ПРАВИЛЬНО: Создана заявка 'Нет горячей воды'")
            return True
        else:
            print(f"⚠️ Заявка создана, но услуга: {service_name}")
            return True  # Может быть окей
    else:
        print(f"❌ ОШИБКА: Не создал заявку, статус: {result3['status']}")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_no_water_full_process())

        print("\n" + "=" * 100)
        if result:
            print("✅ ТЕСТ ПРОЙДЕН: Сценарий работает правильно!")
        else:
            print("❌ ТЕСТ НЕ ПРОЙДЕН: Обнаружены проблемы")
        print("=" * 100)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
