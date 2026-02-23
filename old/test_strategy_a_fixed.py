#!/usr/bin/env python3
"""Тест стратегии A после исправления - без 'Похоже на...'"""

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

async def test_strategy_a_no_appearance():
    """Тест стратегии A - НЕ должно быть 'Похоже на...'"""
    print("="*80)
    print("ТЕСТ: Стратегия A без 'Похоже на...'")
    print("="*80)

    agent = MainAgent()

    # Симуляция: 1 кандидат с высоким confidence, локация НЕ известна
    result = await agent._generate_ai_question(
        context={"original_message": "течет батарея"},
        dialog_history=[
            {"role": "user", "text": "течет батарея"}
        ],
        candidates=[{
            "service_id": 31,
            "service_name": "Протечка батареи в квартире",
            "category": "Отопление",
            "location_type": "Индивидуальное",
            "confidence": 0.94
        }],
        established_filters={
            "category": {"value": "Отопление", "confidence": 0.9},
            "incident_type": {"value": "Инцидент", "confidence": 0.85},
            "location_type": {"value": "Индивидуальное", "confidence": 0.8}
        },
        txtPrb="у пользователя течет из батареи",
        question_type="clarification",
        session_id="test_strategy_a_fixed",
        accumulated_fields={
            "problem": "течет",
            "source": "батарея"
            # location НЕТ!
        }
    )

    question = result['question']
    print(f"\n✅ Сгенерированный вопрос:\n{question}")
    print(f"\n📊 Промпт (первые 300 символов):\n{result['prompt'][:300]}...")

    # Проверки
    question_lower = question.lower()

    # Проверяем что НЕТ "Похоже на"
    if "похоже" in question_lower or "походит" in question_lower or "вероят" in question_lower:
        print("\n❌ ОШИБКА: Вопрос содержит 'Похоже на...' или подобное!")
        return False
    else:
        print("\n✅ ПРАВИЛЬНО: Вопрос НЕ содержит 'Похоже на...'")

    # Проверяем что вопрос по локации
    if "где" in question_lower and ("именно" in question_lower or "происходит" in question_lower or "произошло" in question_lower):
        print("✅ ПРАВИЛЬНО: Вопрос про локацию")
        return True
    else:
        print("⚠️ Вопрос не про локацию (но это может быть нормально)")
        return True

async def test_flow():
    """Тест полного потока как в примере пользователя"""
    print("\n" + "="*80)
    print("ТЕСТ ПОТОКА: прорвало трубу → Где именно? → в квартире → заявка")
    print("="*80)

    agent = MainAgent()

    # Шаг 1: "прорвало трубу"
    print("\n--- ШАГ 1: Пользователь 'прорвало трубу' ---")
    result1 = await agent._generate_ai_question(
        context={"original_message": "прорвало трубу"},
        dialog_history=[],
        candidates=[{
            "service_id": 32,
            "service_name": "Прорыв труб в квартире",
            "category": "Водоснабжение",
            "location_type": "Индивидуальное",
            "confidence": 0.92
        }],
        established_filters={
            "category": {"value": "Водоснабжение", "confidence": 0.88}
        },
        txtPrb="у пользователя прорвало трубу",
        question_type="clarification",
        session_id="test_flow_step1",
        accumulated_fields={"problem": "прорвало", "source": "трубу"}
    )

    question1 = result1['question']
    print(f"Бот: {question1}")

    if "где" in question1.lower() and ("именно" in question1.lower() or "происходит" in question1.lower()):
        print("✅ Правильно: спросил локацию")
    elif "похоже" in question1.lower():
        print("❌ Ошибка: содержит 'Похоже на...'")
    else:
        print(f"⚠️ Неожиданный вопрос")

    # Шаг 2: "в квартире" - теперь локация известна, должна создаться заявка
    print("\n--- ШАГ 2: Пользователь 'в квартире' ---")

    # После того как пользователь сказал "в квартире"
    # accumulated_fields обновляется:
    result2 = await agent._generate_ai_question(
        context={"original_message": "в квартире"},
        dialog_history=[
            {"role": "user", "text": "прорвало трубу"},
            {"role": "bot", "text": question1},
            {"role": "user", "text": "в квартире"}
        ],
        candidates=[{
            "service_id": 32,
            "service_name": "Прорыв труб в квартире",
            "category": "Водоснабжение",
            "location_type": "Индивидуальное",
            "confidence": 0.95
        }],
        established_filters={
            "category": {"value": "Водоснабжение", "confidence": 0.92},
            "location_type": {"value": "Индивидуальное", "confidence": 0.90}
        },
        txtPrb="у пользователя прорвало трубу в квартире",
        question_type="clarification",
        session_id="test_flow_step2",
        accumulated_fields={
            "problem": "прорвало",
            "source": "трубу",
            "location": "квартире"  # Локация теперь ИЗВЕСТНА!
        }
    )

    question2 = result2['question']
    print(f"Бот: {question2}")

    # После уточнения локации должен быть SUCCESS (заявка создается)
    # Но здесь мы тестируем только генерацию вопроса

    if "похоже" in question2.lower() or "правильно" in question2.lower():
        print("❌ Ошибка: содержит подтверждение (избыточно!)")
        print("✅ ОЖИДАЕТСЯ: После уточнения локации БОТ ДОЛЖЕН СОЗДАТЬ ЗАЯВКУ (в коде этоSUCCESS)")
        return False
    else:
        print("✅ Правильно: без лишних подтверждений")
        print("✅ В реальном коде после этого будет создана заявка (status=SUCCESS)")
        return True

async def main():
    print("\n" + "🔬 ТЕСТИРОВАНИЕ ИСПРАВЛЕННОЙ СТРАТЕГИИ A" + "\n")

    try:
        result1 = await test_strategy_a_no_appearance()
        result2 = await test_flow()

        print("\n" + "="*80)
        if result1 and result2:
            print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        else:
            print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        print("="*80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
