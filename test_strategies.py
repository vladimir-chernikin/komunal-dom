#!/usr/bin/env python3
"""Тест стратегий A/B/C/NONE с established_filters"""

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

async def test_strategy_a():
    """Тест стратегии A: 1 кандидат с высоким confidence"""
    print("="*80)
    print("ТЕСТ СТРАТЕГИИ A: 1 кандидат")
    print("="*80)

    agent = MainAgent()

    # Симулируем результат поиска с 1 кандидатом
    result = await agent._generate_ai_question(
        context={"original_message": "течет батарея в зале"},
        dialog_history=[
            {"role": "user", "text": "течет батарея"},
            {"role": "bot", "text": "Где именно это происходит?"},
            {"role": "user", "text": "в зале"}
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
            "incident_type": {"value": "Инцидент", "confidence": 0.85}
        },
        txtPrb="у пользователя течет из батареи (отопление) в зале",
        question_type="clarification",
        session_id="test_strategy_a",
        accumulated_fields={
            "problem": "течет",
            "source": "батарея",
            "location": "зал"
        }
    )

    print(f"\n✅ Сгенерированный вопрос:\n{result['question']}")
    print(f"\n📊 Стратегия: A (1 кандидат, 94% confidence)")

    # Проверки
    question_lower = result['question'].lower()

    if "правильно" in question_lower or "верно" in question_lower or "подтверд" in question_lower:
        print("✅ Стратегия A: Бот задал подтверждающий вопрос")
    elif "заявк" in question_lower or "создать" in question_lower:
        print("✅ Стратегия A: Бот предложил создать заявку")
    else:
        print(f"⚠️ Стратегия A: Неожиданный вопрос")

    return result

async def test_strategy_b():
    """Тест стратегии B: 2-10 кандидатов"""
    print("\n" + "="*80)
    print("ТЕСТ СТРАТЕГИИ B: 5 кандидатов")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "проблема с водой"},
        dialog_history=[
            {"role": "user", "text": "проблема с водой"}
        ],
        candidates=[
            {"service_id": 32, "service_name": "Прорыв труб в квартире", "category": "Водоснабжение", "location_type": "Индивидуальное", "confidence": 0.75},
            {"service_id": 33, "service_name": "Общедомовой прорыв труб", "category": "Водоснабжение", "location_type": "Общедомовое", "confidence": 0.72},
            {"service_id": 31, "service_name": "Протечка батареи", "category": "Отопление", "location_type": "Индивидуальное", "confidence": 0.68},
            {"service_id": 38, "service_name": "Протечки сантехники", "category": "Водоснабжение", "location_type": "Индивидуальное", "confidence": 0.65},
            {"service_id": 30, "service_name": "Протечка отопления общедомовой", "category": "Отопление", "location_type": "Общедомовое", "confidence": 0.62}
        ],
        established_filters={},  # Нет установленных фильтров
        txtPrb="у пользователя проблема с водой",
        question_type="clarification",
        session_id="test_strategy_b",
        accumulated_fields={"problem": "проблема"}
    )

    print(f"\n✅ Сгенерированный вопрос:\n{result['question']}")
    print(f"\n📊 Стратегия: B (5 кандидатов)")

    # Проверки
    question_lower = result['question'].lower()

    if "где" in question_lower or "мест" in question_lower:
        print("✅ Стратегия B: Бот уточняет локацию")
    elif "какая" in question_lower or "систем" in question_lower or "категор" in question_lower:
        print("✅ Стратегия B: Бот уточняет категорию")
    else:
        print(f"⚠️ Стратегия B: Другой вопрос")

    return result

async def test_with_established_filters():
    """Тест с установленными фильтрами"""
    print("\n" + "="*80)
    print("ТЕСТ: УЖЕ ИЗВЕСТНЫЕ ФИЛЬТРЫ")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "течет"},
        dialog_history=[{"role": "user", "text": "течет"}],
        candidates=[
            {"service_id": 32, "service_name": "Прорыв труб в квартире", "category": "Водоснабжение", "location_type": "Индивидуальное", "confidence": 0.75},
            {"service_id": 31, "service_name": "Протечка батареи", "category": "Отопление", "location_type": "Индивидуальное", "confidence": 0.70}
        ],
        established_filters={
            "location_type": {"value": "Индивидуальное", "confidence": 0.9}
        },
        txtPrb="у пользователя течет",
        question_type="clarification",
        session_id="test_filters",
        accumulated_fields={"problem": "течет"}
    )

    print(f"\n✅ Сгенерированный вопрос:\n{result['question']}")
    print(f"\n📊 Установленные фильтры: location_type=Индивидуальное (90%)")

    # Проверки
    question_lower = result['question'].lower()

    if "где" in question_lower or "мест" in question_lower or "локаци" in question_lower:
        print("❌ ОШИБКА: Бот спросил про локацию (хотя она известна!)")
    else:
        print("✅ ПРАВИЛЬНО: Бот НЕ спросил про известную локацию")

    return result

async def main():
    print("\n" + "🔬 ТЕСТИРОВАНИЕ СТРАТЕГИЙ A/B/C/NONE" + "\n")

    try:
        # Тест 1: Стратегия A
        await test_strategy_a()

        # Тест 2: Стратегия B
        await test_strategy_b()

        # Тест 3: С установленными фильтрами
        await test_with_established_filters()

        print("\n" + "="*80)
        print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("="*80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
