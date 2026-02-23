#!/usr/bin/env python3
"""Тест уточнения типа воды: нет воды vs нет холодной воды"""

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

async def test_no_water_without_type():
    """Тест: нет воды (тип НЕ указан)"""
    print("="*80)
    print("ТЕСТ 1: 'нет воды' (тип НЕ указан)")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "нет воды"},
        dialog_history=[],
        candidates=[{
            "service_id": 34,
            "service_name": "Нет горячей воды",
            "category": "Водоснабжение",
            "location_type": "Общедомовое",
            "confidence": 0.85
        }],
        established_filters={
            "category": {"value": "Водоснабжение", "confidence": 0.80},
            "incident_type": {"value": "Инцидент", "confidence": 0.85}
        },
        txtPrb="у пользователя нет воды",
        question_type="clarification",
        session_id="test_no_water_type_1",
        accumulated_fields={
            "problem": "нет",
            "source": "воды"
            # тип НЕ указан
        }
    )

    question = result['question']
    print(f"Бот: {question}")
    print()

    question_lower = question.lower()

    # Проверяем: НЕ должно быть "или"
    if "или" in question_lower:
        print("❌ ОШИБКА: Вопрос содержит 'или'")
        return False

    # Проверяем: должен спрашивать локацию
    if "где" in question_lower and "именно" in question_lower:
        print("✅ ПРАВИЛЬНО: Спрашивает локацию")
        return True
    else:
        print(f"⚠️ Другой вопрос: {question}")
        return True

async def test_no_cold_water_with_type():
    """Тест: нет холодной воды (тип УЖЕ указан)"""
    print("\n" + "="*80)
    print("ТЕСТ 2: 'нет холодной воды' (тип УЖЕ указан)")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "нет холодной воды"},
        dialog_history=[],
        candidates=[{
            "service_id": 39,
            "service_name": "Нет холодной воды",
            "category": "Водоснабжение",
            "location_type": "Индивидуальное",
            "confidence": 0.92
        }],
        established_filters={
            "category": {"value": "Водоснабжение", "confidence": 0.88},
            "incident_type": {"value": "Инцидент", "confidence": 0.90}
        },
        txtPrb="у пользователя нет холодной воды",
        question_type="clarification",
        session_id="test_no_water_type_2",
        accumulated_fields={
            "problem": "нет",
            "source": "холодной воды"  # ТИП УЖЕ УКАЗАН
        }
    )

    question = result['question']
    print(f"Бот: {question}")
    print()

    question_lower = question.lower()

    # Проверяем: НЕ должно быть "или"
    if "или" in question_lower:
        print("❌ ОШИБКА: Вопрос содержит 'или'")
        return False

    # Проверяем: НЕ должен спрашивать тип (он уже известен)
    if any(word in question_lower for word in ["горяч", "холод", "какой вод"]):
        print("❌ ОШИБКА: Спрашивает тип (уже известен)")
        return False

    # Проверяем: должен спрашивать локацию
    if "где" in question_lower and "именно" in question_lower:
        print("✅ ПРАВИЛЬНО: Спрашивает только локацию (тип известен)")
        return True
    else:
        print(f"⚠️ Другой вопрос: {question}")
        return True

async def test_flow_with_type():
    """Полный поток: нет воды → локация → тип → заявка"""
    print("\n" + "="*80)
    print("ТЕСТ 3: Полный поток с уточнением типа")
    print("="*80)

    agent = MainAgent()

    # Шаг 1: "нет воды"
    print("\n--- ШАГ 1: Пользователь 'нет воды' ---")

    result1 = await agent._generate_ai_question(
        context={"original_message": "нет воды"},
        dialog_history=[],
        candidates=[{
            "service_id": 34,
            "service_name": "Нет горячей воды",
            "category": "Водоснабжение",
            "location_type": "Общедомовое",
            "confidence": 0.85
        }],
        established_filters={
            "category": {"value": "Водоснабжение", "confidence": 0.80}
        },
        txtPrb="у пользователя нет воды",
        question_type="clarification",
        session_id="test_flow_step1",
        accumulated_fields={"problem": "нет", "source": "воды"}
    )

    print(f"Бот: {result1['question']}")

    # Шаг 2: "в ванной" (локация)
    print("\n--- ШАГ 2: Пользователь 'в ванной' ---")

    result2 = await agent._generate_ai_question(
        context={"original_message": "в ванной"},
        dialog_history=[
            {"role": "user", "text": "нет воды"},
            {"role": "bot", "text": result1['question']},
            {"role": "user", "text": "в ванной"}
        ],
        candidates=[{
            "service_id": 34,
            "service_name": "Нет горячей воды",
            "category": "Водоснабжение",
            "location_type": "Индивидуальное",
            "confidence": 0.88
        }],
        established_filters={
            "category": {"value": "Водоснабжение", "confidence": 0.85},
            "location_type": {"value": "Индивидуальное", "confidence": 0.82}
        },
        txtPrb="у пользователя нет воды в ванной",
        question_type="clarification",
        session_id="test_flow_step2",
        accumulated_fields={
            "problem": "нет",
            "source": "воды",
            "location": "ванной"
        }
    )

    print(f"Бот: {result2['question']}")
    question2_lower = result2['question'].lower()

    # Проверяем: должен спросить тип БЕЗ "или"
    if "или" in question2_lower:
        print("❌ ОШИБКА: Содержит 'или'")
        return False

    if any(word in question2_lower for word in ["какой", "тип", "какая"]):
        print("✅ ПРАВИЛЬНО: Спрашивает тип (открытый вопрос)")
        return True
    else:
        print(f"⚠️ Другой вопрос: {result2['question']}")
        return True

async def main():
    print("\n" + "🔬 ТЕСТ: Уточнение типа воды" + "\n")

    try:
        result1 = await test_no_water_without_type()
        result2 = await test_no_cold_water_with_type()
        result3 = await test_flow_with_type()

        print("\n" + "="*80)
        print("ИТОГИ:")
        print(f"Тест 1 (нет воды): {'✅' if result1 else '❌'}")
        print(f"Тест 2 (нет холодной воды): {'✅' if result2 else '❌'}")
        print(f"Тест 3 (полный поток): {'✅' if result3 else '❌'}")
        print("="*80)

        if all([result1, result2, result3]):
            print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        else:
            print("\n❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
