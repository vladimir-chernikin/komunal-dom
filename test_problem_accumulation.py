#!/usr/bin/env python3
"""Тест ProblemAccumulationService для сценария "нет воды" → "в квартире" """

import asyncio
import sys
import os

# Django setup
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from problem_accumulation_service import ProblemAccumulationService
from ai_agent_service import AIAgentService

async def test_problem_accumulation():
    """Тестируем накопление проблемы"""
    print("=" * 100)
    print("ТЕСТ ProblemAccumulationService")
    print("=" * 100)

    # Инициализируем сервисы
    ai_agent = AIAgentService()
    accumulation_service = ProblemAccumulationService(ai_agent)

    # ========== ШАГ 1: "нет воды" ==========
    print("\n--- ШАГ 1: 'нет воды' ---")

    result1 = await accumulation_service.extract_and_accumulate(
        message_text="нет воды",
        current_problem="",  # Пусто на начало
        bot_question=None,
        dialog_history=[],
        session_id="test_acc_1"
    )

    print(f"is_meaningful: {result1['is_meaningful']}")
    print(f"new_info: {result1['new_info']}")
    print(f"updated_problem: {result1['updated_problem']}")
    print(f"fields: {result1['fields']}")

    current_problem = result1['updated_problem']

    # ========== ШАГ 2: "в квартире" ==========
    print("\n--- ШАГ 2: 'в квартире' (ответ на 'Где именно?') ---")

    result2 = await accumulation_service.extract_and_accumulate(
        message_text="в квартире",
        current_problem=current_problem,
        bot_question="Где именно нет воды?",
        dialog_history=[
            {"role": "user", "text": "нет воды"},
            {"role": "bot", "text": "Где именно нет воды?"}
        ],
        session_id="test_acc_2"
    )

    print(f"is_meaningful: {result2['is_meaningful']}")
    print(f"new_info: {result2['new_info']}")
    print(f"updated_problem: {result2['updated_problem']}")
    print(f"fields: {result2['fields']}")

    # ========== ПРОВЕРКА ==========
    print("\n" + "=" * 100)
    print("ПРОВЕРКА РЕЗУЛЬТАТОВ")
    print("=" * 100)

    expected_problem = "у пользователя нет воды в квартире"
    actual_problem = result2['updated_problem']

    print(f"\nОжидалось: '{expected_problem}'")
    print(f"Получено:  '{actual_problem}'")

    if expected_problem == actual_problem:
        print("\n✅ УСПЕХ! ProblemAccumulationService работает правильно")
        return True
    else:
        print("\n❌ ОШИБКА! ProblemAccumulationService потерял контекст")
        print(f"\nРазличие:")
        print(f"  Ожидалось сохранение 'нет воды' + добавление 'в квартире'")
        print(f"  Но получил: '{actual_problem}'")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(test_problem_accumulation())

        if not result:
            print("\n" + "=" * 100)
            print("НЕОБХОДИМО ИСПРАВИТЬ ПРОМПТ В БД!")
            print("=" * 100)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
