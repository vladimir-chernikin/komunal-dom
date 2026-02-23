#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки "течет батарея"
"""

import asyncio
import sys
sys.path.insert(0, '/var/www/komunal-dom_ru')

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from main_agent import MainAgent
from message_handler_service import MessageHandlerService
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test_battery_leak():
    """Тестирование 'течет батарея'"""

    print("\n" + "="*60)
    print("ТЕСТ: 'течет батарея'")
    print("="*60 + "\n")

    # Инициализируем MainAgent
    main_agent = MainAgent()

    # Имитируем входящие параметры
    user_context = {
        'user_id': 'test_user_123',
        'session_id': 'test_battery_session',
        'dialog_history': [],
        'is_followup': False
    }

    result = await main_agent.process_service_detection(
        message_text="течет батарея",
        user_context=user_context
    )

    print("\n" + "="*60)
    print("РЕЗУЛЬТ:")
    print("="*60)
    print(f"Status: {result.get('status')}")
    print(f"Response: {result.get('response')}")

    if 'metadata' in result:
        metadata = result['metadata']
        print(f"\n--- Metadata ---")
        print(f"txtPrb: {metadata.get('txtPrb')}")

        accumulated = metadata.get('accumulated_fields', {})
        print(f"\naccumulated_fields:")
        if accumulated:
            for key, value in accumulated.items():
                print(f"  {key}: {value}")
        else:
            print("  (пусто)")

        established = metadata.get('established_filters', {})
        print(f"\nestablished_filters:")
        if established:
            for key, value in established.items():
                print(f"  {key}: {value}")
        else:
            print("  (пусто)")

    if result.get('service_detected'):
        sd = result['service_detected']
        print(f"\n--- Service Detected ---")
        print(f"Service ID: {sd.get('service_id')}")
        print(f"Service name: {sd.get('service_name')}")
        print(f"Confidence: {sd.get('confidence')}")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(test_battery_leak())
