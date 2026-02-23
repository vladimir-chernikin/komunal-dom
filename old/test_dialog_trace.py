#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Полная трассировка диалога для отладки
Диалог: "привет" → "у меня капает" → "я же сказал, у меня капает!"
"""

import asyncio
import sys
import os
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from main_agent import MainAgent
from problem_accumulation_service import ProblemAccumulationService
from ai_agent_service import AIAgentService
import json

async def debug_dialog():
    """Полная отладка диалога"""

    print("=" * 80)
    print("ПОЛНАЯ ТРАССИРОВКА ДИАЛОГА")
    print("=" * 80)

    # Создаем сервисы
    ai_service = AIAgentService(provider='yandexgpt')
    main_agent = MainAgent()
    problem_service = ProblemAccumulationService(ai_agent_service=ai_service)

    # Имитация диалога
    session_id = "debug_test_session"

    # СООБЩЕНИЕ 1: "привет"
    print("\n" + "=" * 80)
    print("СООБЩЕНИЕ 1: 'привет'")
    print("=" * 80)

    dialog_history_1 = []

    result_1 = await main_agent.process_service_detection(
        message_text="привет",
        user_context={}
    )

    print(f"\n[RESULT 1]")
    print(f"  Status: {result_1.get('status')}")
    print(f"  Message: {result_1.get('message')}")
    print(f"  Candidates: {len(result_1.get('candidates', []))}")
    print(f"  _metadata keys: {list(result_1.get('_metadata', {}).keys())}")

    if '_metadata' in result_1:
        metadata = result_1['_metadata']
        print(f"\n  [METADATA]")
        print(f"    txtPrb: '{metadata.get('txtPrb', 'N/A')[:100]}'")
        print(f"    accumulated_fields: {json.dumps(metadata.get('accumulated_fields', {}), ensure_ascii=False)}")
        print(f"    established_filters: {json.dumps(metadata.get('established_filters', {}), ensure_ascii=False)}")
        print(f"    microservices_results: {list(metadata.get('microservices_results', {}).keys())}")

        # Показываем результаты микросервисов
        if 'microservices_results' in metadata:
            micro = metadata['microservices_results']
            for service_name, service_result in micro.items():
                print(f"\n  [{service_name}]")
                print(f"    Status: {service_result.get('status')}")
                print(f"    Candidates: {len(service_result.get('candidates', []))}")
                if service_result.get('candidates'):
                    for i, cand in enumerate(service_result['candidates'][:3]):
                        print(f"      [{i+1}] {cand.get('service_name')} (confidence: {cand.get('confidence')})")

    # СООБЩЕНИЕ 2: "у меня капает"
    print("\n" + "=" * 80)
    print("СООБЩЕНИЕ 2: 'у меня капает'")
    print("=" * 80)

    result_2 = await main_agent.process_service_detection(
        message_text="у меня капает",
        user_context={}
    )

    print(f"\n[RESULT 2]")
    print(f"  Status: {result_2.get('status')}")
    print(f"  Message: {result_2.get('message')}")
    print(f"  Candidates: {len(result_2.get('candidates', []))}")
    print(f"  _metadata keys: {list(result_2.get('_metadata', {}).keys())}")

    if '_metadata' in result_2:
        metadata = result_2['_metadata']
        print(f"\n  [METADATA]")
        print(f"    txtPrb: '{metadata.get('txtPrb', 'N/A')[:150]}'")
        print(f"    accumulated_fields: {json.dumps(metadata.get('accumulated_fields', {}), ensure_ascii=False, indent=4)}")
        print(f"    established_filters: {json.dumps(metadata.get('established_filters', {}), ensure_ascii=False, indent=4)}")

        # Показываем результаты микросервисов
        if 'microservices_results' in metadata:
            micro = metadata['microservices_results']
            print(f"\n  [MICROSERVICES RESULTS]")
            for service_name, service_result in micro.items():
                print(f"\n    {service_name}:")
                print(f"      Status: {service_result.get('status')}")
                print(f"      Candidates: {len(service_result.get('candidates', []))}")
                if service_result.get('candidates'):
                    for i, cand in enumerate(service_result['candidates'][:5]):
                        print(f"        [{i+1}] {cand.get('service_name')} (conf: {cand.get('confidence')}, source: {cand.get('source')})")

    # ПРОВЕРКА: txtPrb через ProblemAccumulationService
    print("\n  [ПРОВЕРКА: ProblemAccumulationService]")
    direct_txtPrb = await problem_service.extract_and_accumulate(
        message_text="у меня капает",
        current_problem="",
        bot_question=result_1.get('message', ''),
        dialog_history=None,
        session_id=session_id
    )
    print(f"    Direct txtPrb: '{direct_txtPrb.get('updated_problem', 'N/A')[:150]}'")
    print(f"    Is meaningful: {direct_txtPrb.get('is_meaningful', 'N/A')}")

    # СООБЩЕНИЕ 3: "я же сказал, у меня капает!"
    print("\n" + "=" * 80)
    print("СООБЩЕНИЕ 3: 'я же сказал, у меня капает!'")
    print("=" * 80)

    result_3 = await main_agent.process_service_detection(
        message_text="я же сказал, у меня капает!",
        user_context={}
    )

    print(f"\n[RESULT 3]")
    print(f"  Status: {result_3.get('status')}")
    print(f"  Message: {result_3.get('message')}")
    print(f"  Candidates: {len(result_3.get('candidates', []))}")

    if '_metadata' in result_3:
        metadata = result_3['_metadata']
        print(f"\n  [METADATA]")
        print(f"    txtPrb: '{metadata.get('txtPrb', 'N/A')[:150]}'")
        print(f"    accumulated_fields: {json.dumps(metadata.get('accumulated_fields', {}), ensure_ascii=False, indent=4)}")
        print(f"    established_filters: {json.dumps(metadata.get('established_filters', {}), ensure_ascii=False, indent=4)}")

    print("\n" + "=" * 80)
    print("КОНЕЦ ТРАССИРОВКИ")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(debug_dialog())
