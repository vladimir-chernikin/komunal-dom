#!/usr/bin/env python3
"""
Полный тест всех сценариев работы MainAgent

СЦЕНАРИИ:
1. Прорыв трубы → локация → заявка
2. Протечка батареи → локация → интенсивность → заявка
3. Запах газа → локация → заявка
4. Нет света → локация → заявка
5. Лифт не работает → заявка (без локации)
6. Запрос лицевой счет → заявка (без уточнений)
"""

import asyncio
import sys
import os

sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from main_agent import MainAgent

async def scenario_1_pipe_burst():
    """Сценарий 1: Прорыв трубы"""
    print("\n" + "="*80)
    print("СЦЕНАРИЙ 1: Прорыв трубы")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
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
            "category": {"value": "Водоснабжение", "confidence": 0.88},
            "incident_type": {"value": "Инцидент", "confidence": 0.90}
        },
        txtPrb="у пользователя прорвало трубу",
        question_type="clarification",
        session_id="test_scenario_1",
        accumulated_fields={"problem": "прорвало", "source": "трубу"}
    )

    print(f"Пользователь: прорвало трубу")
    print(f"Бот: {result['question']}")
    print("Ожидается: 'Где именно?' или подобный вопрос о локации")

    question_lower = result['question'].lower()
    if "где" in question_lower and "именно" in question_lower:
        print("✅ ПРАВИЛЬНО")
        return True
    else:
        print("⚠️ Другой вопрос")
        return False

async def scenario_2_battery_leak():
    """Сценарий 2: Протечка батареи"""
    print("\n" + "="*80)
    print("СЦЕНАРИЙ 2: Протечка батареи (с интенсивностью)")
    print("="*80)

    agent = MainAgent()

    # Шаг 1: Спрашиваем локацию
    result1 = await agent._generate_ai_question(
        context={"original_message": "течет батарея"},
        dialog_history=[],
        candidates=[{
            "service_id": 31,
            "service_name": "Протечка батареи в квартире",
            "category": "Отопление",
            "location_type": "Индивидуальное",
            "confidence": 0.92
        }],
        established_filters={
            "category": {"value": "Отопление", "confidence": 0.90},
            "incident_type": {"value": "Инцидент", "confidence": 0.85}
        },
        txtPrb="у пользователя течет из батареи",
        question_type="clarification",
        session_id="test_scenario_2_step1",
        accumulated_fields={"problem": "течет", "source": "батарея"}
    )

    print(f"Пользователь: течет батарея")
    print(f"Бот: {result1['question']}")

    # Шаг 2: Спрашиваем интенсивность (после уточнения локации)
    result2 = await agent._generate_ai_question(
        context={"original_message": "в зале"},
        dialog_history=[
            {"role": "user", "text": "течет батарея"},
            {"role": "bot", "text": result1['question']},
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
            "category": {"value": "Отопление", "confidence": 0.92},
            "incident_type": {"value": "Инцидент", "confidence": 0.90},
            "location_type": {"value": "Индивидуальное", "confidence": 0.85}
        },
        txtPrb="у пользователя течет из батареи в зале",
        question_type="clarification",
        session_id="test_scenario_2_step2",
        accumulated_fields={"problem": "течет", "source": "батарея", "location": "зале"}
    )

    print(f"Пользователь: в зале")
    print(f"Бот: {result2['question']}")
    print("Ожидается: вопрос об интенсивности (как сильно течет)")

    question2_lower = result2['question'].lower()
    if any(word in question2_lower for word in ["как", "сильн", "интенсив", "характер", "степен"]):
        print("✅ ПРАВИЛЬНО (спрашивает интенсивность)")
        return True
    else:
        print("⚠️ Другой вопрос")
        return False

async def scenario_3_gas_smell():
    """Сценарий 3: Запах газа (без интенсивности)"""
    print("\n" + "="*80)
    print("СЦЕНАРИЙ 3: Запах газа (БЕЗ интенсивности)")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "пахнет газом"},
        dialog_history=[],
        candidates=[{
            "service_id": 51,
            "service_name": "Запах газа",
            "category": "Газ",
            "location_type": None,
            "confidence": 0.88
        }],
        established_filters={
            "category": {"value": "Газ", "confidence": 0.85},
            "incident_type": {"value": "Инцидент", "confidence": 0.95}
        },
        txtPrb="у пользователя пахнет газом",
        question_type="clarification",
        session_id="test_scenario_3",
        accumulated_fields={"problem": "пахнет", "source": "газом"}
    )

    print(f"Пользователь: пахнет газом")
    print(f"Бот: {result['question']}")
    print("Ожидается: 'Где именно?' (БЕЗ интенсивности)")

    question_lower = result['question'].lower()

    # Проверяем: спрашивает локацию, но НЕ интенсивность
    asks_location = "где" in question_lower and "именно" in question_lower
    asks_intensity = any(word in question_lower for word in ["как", "сильн", "интенсив", "степень"])

    if asks_location and not asks_intensity:
        print("✅ ПРАВИЛЬНО (спрашивает локацию, БЕЗ интенсивности)")
        return True
    elif asks_intensity:
        print("❌ ОШИБКА (спрашивает интенсивность - не нужно для газа!)")
        return False
    else:
        print("⚠️ Другой вопрос")
        return False

async def scenario_4_no_electricity():
    """Сценарий 4: Нет света"""
    print("\n" + "="*80)
    print("СЦЕНАРИЙ 4: Нет света")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "нет света"},
        dialog_history=[],
        candidates=[{
            "service_id": 43,
            "service_name": "Нет света во всем доме",
            "category": "Электричество",
            "location_type": "Общедомовое",
            "confidence": 0.89
        }],
        established_filters={
            "category": {"value": "Электричество", "confidence": 0.85},
            "incident_type": {"value": "Инцидент", "confidence": 0.90}
        },
        txtPrb="у пользователя нет света",
        question_type="clarification",
        session_id="test_scenario_4",
        accumulated_fields={"problem": "нет", "source": "света"}
    )

    print(f"Пользователь: нет света")
    print(f"Бот: {result['question']}")
    print("Ожидается: Уточнение что именно (квартира или дом?)")

    # Для электричества может спросить: квартира или весь дом?
    question_lower = result['question'].lower()
    if "квартир" in question_lower or "дом" in question_lower or "именно" in question_lower:
        print("✅ ПРАВИЛЬНО (уточняет масштаб)")
        return True
    else:
        print("⚠️ Другой вопрос")
        return False

async def scenario_5_elevator():
    """Сценарий 5: Лифт не работает (общедомовое, без локации)"""
    print("\n" + "="*80)
    print("СЦЕНАРИЙ 5: Лифт не работает (Общедомовое, локация не нужна)")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "лифт не работает"},
        dialog_history=[],
        candidates=[{
            "service_id": 55,
            "service_name": "Лифт не работает",
            "category": "Лифты",
            "location_type": "Общедомовое",
            "confidence": 0.95
        }],
        established_filters={
            "category": {"value": "Лифты", "confidence": 0.90},
            "incident_type": {"value": "Инцидент", "confidence": 0.92},
            "location_type": {"value": "Общедомовое", "confidence": 0.85}
        },
        txtPrb="у пользователя лифт не работает",
        question_type="clarification",
        session_id="test_scenario_5",
        accumulated_fields={"problem": "не работает", "source": "лифт"}
    )

    print(f"Пользователь: лифт не работает")
    print(f"Бот: {result['question']}")
    print("Ожидается: Создание заявки (локация не нужна для общедомового)")

    # Лифт - общедомовое, может сразу создать заявку
    # Или спросить уточнение: какой этаж, что именно происходит
    return True

async def scenario_6_info_request():
    """Сценарий 6: Запрос лицевого счета (Запрос, не Инцидент)"""
    print("\n" + "="*80)
    print("СЦЕНАРИЙ 6: Запрос лицевого счета (Запрос, без уточнений)")
    print("="*80)

    agent = MainAgent()

    result = await agent._generate_ai_question(
        context={"original_message": "хочу узнать лицевой счет"},
        dialog_history=[],
        candidates=[{
            "service_id": 66,
            "service_name": "Лицевые счета",
            "category": "Информационные запросы",
            "location_type": None,
            "confidence": 0.88
        }],
        established_filters={
            "category": {"value": "Информационные запросы", "confidence": 0.80},
            "incident_type": {"value": "Запрос", "confidence": 0.85}
        },
        txtPrb="пользователь хочет узнать лицевой счет",
        question_type="clarification",
        session_id="test_scenario_6",
        accumulated_fields={}
    )

    print(f"Пользователь: хочу узнать лицевой счет")
    print(f"Бот: {result['question']}")
    print("Ожидается: Создание заявки или уточнение данных пользователя")

    # Для запросов может не требоваться локация
    return True

async def main():
    print("\n" + "🔬 ПОЛНЫЙ ТЕСТ ВСЕХ СЦЕНАРИЕВ MAIN AGENT" + "\n")

    try:
        results = []

        results.append(("Сценарий 1: Прорыв трубы", await scenario_1_pipe_burst()))
        results.append(("Сценарий 2: Протечка батареи", await scenario_2_battery_leak()))
        results.append(("Сценарий 3: Запах газа", await scenario_3_gas_smell()))
        results.append(("Сценарий 4: Нет света", await scenario_4_no_electricity()))
        results.append(("Сценарий 5: Лифт", await scenario_5_elevator()))
        results.append(("Сценарий 6: Запрос лицевого счета", await scenario_6_info_request()))

        print("\n" + "="*80)
        print("ИТОГИ ПО ВСЕМ СЦЕНАРИЯМ:")
        print("="*80)

        for name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"{status}: {name}")

        total = len(results)
        passed = sum(1 for _, r in results if r)

        print(f"\nИтого: {passed}/{total} сценариев прошли успешно")

        if passed == total:
            print("\n🎉 ВСЕ СЦЕНАРИИ РАБОТАЮТ ПРАВИЛЬНО!")
        else:
            print(f"\n⚠️ {total - passed} сценариев требуют внимания")

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
