#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для отладки category confidence

Проверяет что возвращает FilterDetectionService для category
"""

import sys
import os
import asyncio

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(__file__))

# Инициализация Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from filter_detection_service import FilterDetectionService
from ai_agent_service import AIAgentService


async def test_category_detection():
    """Тест category detection"""

    print("=" * 80)
    print("ТЕСТ: Category Detection - отладка confidence")
    print("=" * 80)

    # Инициализируем AIAgentService
    try:
        ai_agent = AIAgentService()
        print("✅ AIAgentService инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации AIAgentService: {e}")
        return

    # Инициализируем FilterDetectionService
    try:
        filter_service = FilterDetectionService(ai_agent_service=ai_agent)
        print("✅ FilterDetectionService инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации FilterDetectionService: {e}")
        return

    # Текст для теста
    test_text = "течет батарея в зале"

    print(f"\n📝 Тестируем текст: '{test_text}'")

    # Вызываем detect_filters
    try:
        result = await filter_service.detect_filters(
            message_text=test_text,
            dialog_history=[],
            txtPrb="в зале течёт батарея",
            session_id="test_debug",
            message_id=1
        )

        print("\n📊 РЕЗУЛЬТАТ detect_filters:")
        print(f"   Status: {result.get('status')}")
        print(f"   Filters: {result.get('filters')}")

        if result.get('status') == 'success':
            filters = result.get('filters', {})
            details = result.get('details', {})

            print("\n📋 DETAILS:")
            for filter_name, filter_data in details.items():
                print(f"   {filter_name}: {filter_data}")

            # Проверяем category
            if 'category' in details:
                category_data = details['category']
                value = category_data.get('value')
                confidence = category_data.get('confidence')

                print(f"\n🔍 CATEGORY DETECTED:")
                print(f"   Value: {value}")
                print(f"   Confidence: {confidence}")
                print(f"   Type: {type(confidence)}")

                if confidence == 1.0:
                    print("   ✅ Confidence = 1.0 (100%)")
                elif confidence == 0.5:
                    print("   ⚠️ Confidence = 0.5 (50%) - ПАРАДОКС!")
                else:
                    print(f"   ❓ Confidence = {confidence} (неожидаемое значение)")

        else:
            print(f"\n❌ Error: {result.get('error')}")

    except Exception as e:
        import traceback
        print(f"\n❌ ОШИБКА: {e}")
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_category_detection())
