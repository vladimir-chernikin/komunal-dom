#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест сценария 'нет вод' → 'горячей' после исправления location_known

Проверяет что услуга 'Нет горячей воды во всём доме' (ID=34)
больше НЕ задает вопрос 'В одной квартире или во всём доме?'
"""

import asyncio
import sys
sys.path.append('/var/www/komunal-dom_ru')

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from main_agent import MainAgent


async def test_water_service_fix():
    """Тест сценария после исправления"""

    print("=" * 80)
    print("ТЕСТ: 'нет вод' → 'горячий' (ПОСЛЕ ИСПРАВЛЕНИЯ)")
    print("=" * 80)

    agent = MainAgent()

    # ШАГ 1: "нет вод"
    print("\n" + "=" * 80)
    print("ШАГ 1: 'нет вод'")
    print("=" * 80)

    result_1 = await agent.process_service_detection(
        message_text="нет вод",
        user_context={'session_id': 'test_fix_1'}
    )

    print(f"Статус: {result_1.get('status')}")
    print(f"Сообщение: {result_1.get('message', 'N/A')}")

    if result_1.get('candidates'):
        print(f"\nКандидатов: {len(result_1['candidates'])}")
        for i, cand in enumerate(result_1['candidates'][:5]):
            print(f"  {i+1}. ID={cand.get('service_id')}, conf={cand.get('confidence'):.3f}, {cand.get('service_name', 'N/A')[:50]}")

    # ШАГ 2: "горячей"
    print("\n" + "=" * 80)
    print("ШАГ 2: 'горячей'")
    print("=" * 80)

    # ИСПРАВЛЕНО (2026-02-18): Добавляем is_followup=True и dialog_history
    # Чтобы MainAgent знал, что это продолжение диалога
    result_2 = await agent.process_service_detection(
        message_text="горячей",
        user_context={
            'session_id': 'test_fix_1',  # тот же session_id!
            'is_followup': True,  # это followup сообщение!
            'dialog_history': [
                {'role': 'user', 'text': 'нет вод'},
                {'role': 'assistant', 'text': result_1.get('message', '')}
            ]
        }
    )

    print(f"Статус: {result_2.get('status')}")
    print(f"Сообщение: {result_2.get('message', 'N/A')}")

    if result_2.get('candidates'):
        print(f"\nКандидатов: {len(result_2['candidates'])}")
        for i, cand in enumerate(result_2['candidates']):
            loc_type = cand.get('location_type', 'N/A')
            print(f"  {i+1}. ID={cand.get('service_id')}, conf={cand.get('confidence'):.3f}, loc={loc_type}")
            print(f"      {cand.get('service_name', 'N/A')}")
            if cand.get('service_id') == 34:
                print(f"      ✅ ЭТО ПРАВИЛЬНАЯ УСЛУГА!")

    # ПРОВЕРКА РЕЗУЛЬТАТА
    print("\n" + "=" * 80)
    print("ПРОВЕРКА ИСПРАВЛЕНИЯ")
    print("=" * 80)

    # Проверяем что статус SUCCESS
    if result_2.get('status') == 'SUCCESS':
        print("✅ СТАТУС: SUCCESS (правильно)")
    else:
        print(f"❌ СТАТУС: {result_2.get('status')} (ожидается SUCCESS)")

    # Проверяем что найдена правильная услуга
    service_id = result_2.get('service_id')
    if service_id == 34:
        print("✅ УСЛУГА: ID=34 'Нет горячей воды во всём доме' (правильно)")
    else:
        print(f"❌ УСЛУГА: ID={service_id} (ожидается 34)")

    # Проверяем что НЕ спрашивается локация
    message = result_2.get('message', '')
    if 'квартир' not in message.lower() and 'дом' not in message.lower():
        print("✅ ВОПРОС ЛОКАЦИИ: НЕ задан (правильно)")
    else:
        print(f"❌ ВОПРОС ЛОКАЦИИ: Задан '{message}' (НЕ должен задаваться)")

    # Проверяем localization_type у кандидата
    if result_2.get('candidates'):
        candidate = result_2['candidates'][0]
        loc_type = candidate.get('location_type', '')
        if loc_type == 'Общедомовое':
            print(f"✅ LOCALIZATION_TYPE: Общедомовое (правильно)")
        else:
            print(f"❌ LOCALIZATION_TYPE: {loc_type} (ожидается Общедомовое)")

    print("\n" + "=" * 80)
    print("ИТОГОВЫЙ РЕЗУЛЬТАТ")
    print("=" * 80)

    all_passed = (
        result_2.get('status') == 'SUCCESS' and
        result_2.get('service_id') == 34 and
        'квартир' not in message.lower() and
        result_2['candidates'][0].get('location_type') == 'Общедомовое'
    )

    if all_passed:
        print("\n✅✅✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! ✅✅✅")
        print("\nИСПРАВЛЕНИЕ РАБОТАЕТ:")
        print("  - Статус SUCCESS")
        print("  - Найдена правильная услуга ID=34")
        print("  - НЕ задан вопрос 'В одной квартире или во всём доме?'")
        print("  - Услуга имеет localization=Общедомовое")
    else:
        print("\n❌ НЕ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
        print("Возможно требуется дополнительная доработка")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_water_service_fix())
