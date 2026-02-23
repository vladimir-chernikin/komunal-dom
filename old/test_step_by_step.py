#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Детальный анализ сценария "нет вод" → "горячей" по шагам

Цель: Понять почему conf=0.800 на шаге 2 вместо 1.000
"""

import asyncio
import sys
sys.path.append('/var/www/komunal-dom_ru')

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from main_agent import MainAgent
from vector_search_service import VectorSearchService
import numpy as np


async def test_step_by_step():
    """Пошаговый анализ"""

    print("=" * 80)
    print("ПОШАГОВЫЙ АНАЛИЗ: 'нет вод' → 'горячей'")
    print("=" * 80)

    agent = MainAgent()
    vector_service = VectorSearchService()

    # ШАГ 1: "нет вод"
    print("\n" + "=" * 80)
    print("ШАГ 1: 'нет вод'")
    print("=" * 80)

    result_1 = await agent.process_service_detection(
        message_text="нет вод",
        user_context={'session_id': 'test_step_1'}
    )

    print(f"Статус: {result_1.get('status')}")
    print(f"Сообщение: {result_1.get('message', 'N/A')[:100]}")

    if 'candidates' in result_1 and result_1['candidates']:
        print(f"\nКандидатов: {len(result_1['candidates'])}")
        for i, cand in enumerate(result_1['candidates'][:5]):
            print(f"  {i+1}. ID={cand.get('service_id')}, conf={cand.get('confidence'):.3f}, {cand.get('service_name', 'N/A')[:40]}")

    # ШАГ 2: "горячей"
    print("\n" + "=" * 80)
    print("ШАГ 2: 'горячей'")
    print("=" * 80)

    result_2 = await agent.process_service_detection(
        message_text="горячей",
        user_context={'session_id': 'test_step_1'}  # тот же session_id!
    )

    print(f"Статус: {result_2.get('status')}")
    print(f"Сообщение: {result_2.get('message', 'N/A')[:100]}")

    if 'candidates' in result_2 and result_2['candidates']:
        print(f"\nКандидатов: {len(result_2['candidates'])}")
        for i, cand in enumerate(result_2['candidates']):
            print(f"  {i+1}. ID={cand.get('service_id')}, conf={cand.get('confidence'):.3f}, {cand.get('service_name', 'N/A')}")
            if cand.get('service_id') == 34:
                print(f"      ✅ ЭТО ПРАВИЛЬНАЯ УСЛУГА!")

    # ШАГ 3: "нет горячей воды" (сразу)
    print("\n" + "=" * 80)
    print("ШАГ 3: 'нет горячей воды' (сразу в одном сообщении)")
    print("=" * 80)

    result_3 = await agent.process_service_detection(
        message_text="нет горячей воды",
        user_context={'session_id': 'test_step_3'}
    )

    print(f"Статус: {result_3.get('status')}")
    print(f"Сообщение: {result_3.get('message', 'N/A')[:100]}")

    if 'candidates' in result_3 and result_3['candidates']:
        print(f"\nКандидатов: {len(result_3['candidates'])}")
        for i, cand in enumerate(result_3['candidates']):
            print(f"  {i+1}. ID={cand.get('service_id')}, conf={cand.get('confidence'):.3f}, {cand.get('service_name', 'N/A')}")
            if cand.get('service_id') == 34:
                print(f"      ✅ ЭТО ПРАВИЛЬНАЯ УСЛУГА!")

    # АНАЛИЗ
    print("\n" + "=" * 80)
    print("СРАВНИТЕЛЬНЫЙ АНАЛИЗ")
    print("=" * 80)

    conf_step2 = None
    if result_2.get('candidates'):
        for cand in result_2['candidates']:
            if cand.get('service_id') == 34:
                conf_step2 = cand.get('confidence')
                break

    conf_step3 = None
    if result_3.get('candidates'):
        for cand in result_3['candidates']:
            if cand.get('service_id') == 34:
                conf_step3 = cand.get('confidence')
                break

    print(f"""
    Сценарий 1 (по шагам):
    1. "нет вод"
    2. "горячей"
    → Confidence услуги ID=34: {conf_step2 if conf_step2 else 'N/A'}

    Сценарий 2 (сразу):
    1. "нет горячей воды"
    → Confidence услуги ID=34: {conf_step3 if conf_step3 else 'N/A'}

    РАЗНИЦА: {abs((conf_step2 or 0) - (conf_step3 or 0)):.3f}
    """)

    # ПРОВЕРКА: в чем разница в поисковом запросе?
    print("\n" + "=" * 80)
    print("ЧЕМ ОТЛИЧАЮТСЯ ПОИСКОВЫЕ ЗАПРОСЫ?")
    print("=" * 80)

    ai_service = vector_service.ai_service if hasattr(vector_service, 'ai_service') else None
    if ai_service is None:
        from ai_agent_service import AIAgentService
        ai_service = AIAgentService(provider='yandexgpt')

    # Тестируем VectorSearch напрямую
    queries_to_test = [
        "горячей",  # Шаг 2
        "нет горячей воды",  # Шаг 3
    ]

    for query in queries_to_test:
        print(f"\nЗапрос: '{query}'")

        try:
            query_emb, _ = await ai_service.get_embedding(query)
            query_emb = np.array(query_emb, dtype=np.float32)

            # Ищем услугу ID=34
            # ... (можно добавить прямой поиск в БД)
        except Exception as e:
            print(f"  Ошибка: {e}")

    print("\n" + "=" * 80)
    print("ВЫВОДЫ")
    print("=" * 80)

    if conf_step2 and conf_step3:
        if conf_step3 > conf_step2:
            print(f"""
    ✅ ДОКАЗАТЕЛЬСТВО ПОЛУЧЕНО:

    Сценарий "по шагам" (conf={conf_step2:.3f}) ХУЖЕ чем "сразу" (conf={conf_step3:.3f})

    ПРИЧИНА:
    - txtPrb накапливается неправильно
    - На шаге 2 используется только "горячей"
    - На шаге 3 используется полный текст "нет горячей воды"

    РЕШЕНИЕ:
    1. ❌ Понизить порог - НЕ ПРАВИЛЬНО (маскирует проблему)
    2. ✅ Исправить ProblemAccumulationService - ПРАВИЛЬНО
    3. ✅ Исправить WaterTypeQuickCheck - ПРАВИЛЬНО
            """)

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_step_by_step())
