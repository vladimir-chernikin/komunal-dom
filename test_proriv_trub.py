#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для анализа "прорвало трубу"

ЦЕЛЬ: Понять сколько кандидатов находит система и какой у них confidence
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

import asyncio
import json
from main_agent import MainAgent

async def test_proriv_trub():
    """Тестируем что находит MainAgent для 'прорвало трубу'"""

    print("\n" + "=" * 100)
    print("ТЕСТ: 'прорвало трубу'")
    print("=" * 100)

    # Инициализируем MainAgent
    agent = MainAgent()

    # Вызываем метод process_service_detection
    result = await agent.process_service_detection(
        message_text="прорвало трубу",
        user_context={
            'session_id': 'test_proriv_trub',
            'channel': 'test',
            'user_id': 1
        }
    )

    print("\n📊 РЕЗУЛЬТАТ:")
    print(f"Статус: {result.get('status')}")
    print(f"Сообщение: {result.get('message')}")

    if 'candidates' in result:
        candidates = result['candidates']
        print(f"\nНайдено кандидатов: {len(candidates)}")

        print("\n📋 СПИСОК КАНДИДАТОВ:")
        for i, c in enumerate(candidates, 1):
            service_id = c.get('service_id', 'N/A')
            service_name = c.get('service_name', 'Unknown')
            confidence = c.get('confidence', 0)
            source = c.get('source', 'Unknown')

            print(f"\n{i}. service_id={service_id}")
            print(f"   service_name: {service_name}")
            print(f"   confidence: {confidence:.3f}")
            print(f"   source: {source}")

    # Анализ
    print("\n" + "=" * 100)
    print("💡 АНАЛИЗ:")
    print("=" * 100)

    if 'candidates' in result:
        num_candidates = len(result['candidates'])

        if num_candidates == 1:
            print(f"✅ Найден 1 кандидат")
            print(f"   → Должен сработать код на строке 2415: if len(unique_candidates) == 1")
            conf = result['candidates'][0].get('confidence', 0)
            print(f"   → Confidence: {conf:.3f}")

            if conf > 0.80:
                print(f"   → Confidence > 0.80, но есть только 1 кандидат")
                print(f"   → Нужно проверить location в accumulated_fields")

        elif 2 <= num_candidates <= 10:
            print(f"⚠️ Найдено {num_candidates} кандидата(ов)")
            print(f"   → Должен сработать код на строке 2462: elif len(unique_candidates) <= 10")
            print(f"   → Проверим есть ли явный лидер с confidence > 0.80")

            sorted_candidates = sorted(result['candidates'], key=lambda x: x.get('confidence', 0), reverse=True)
            leader = sorted_candidates[0]
            leader_conf = leader.get('confidence', 0)
            second_conf = sorted_candidates[1].get('confidence', 0) if len(sorted_candidates) > 1 else 0

            print(f"\n   Лидер: {leader['service_name'][:40]}")
            print(f"   Confidence лидера: {leader_conf:.3f}")
            print(f"   Confidence второго: {second_conf:.3f}")
            print(f"   Разница: {leader_conf - second_conf:.3f}")

            if leader_conf > 0.80:
                print(f"\n   ❌ НАЙДЕНО ЯВНЫЙ ЛИДЕР с confidence > 0.80!")
                print(f"   → Сработает код на строке 2478: if leader_conf > 0.80")
                print(f"   → Заявка будет создана БЕЗ проверки локации!")
                print(f"   → ЭТО ПРОБЛЕМА!")
            else:
                print(f"\n   ✅ Нет явного лидера (confidence <= 0.80)")
                print(f"   → Будет вызван AI для уточнения")

    print("\n" + "=" * 100)

if __name__ == '__main__':
    asyncio.run(test_proriv_trub())
