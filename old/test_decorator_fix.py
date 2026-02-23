#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест исправления декоратора @database_sync_to_async → @sync_to_async

Проверяет, что FilterDetectionService может корректно загрузить промпты из БД
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from django.conf import settings


async def test_filter_detection():
    """Тест загрузки промптов из БД"""

    print("=" * 80)
    print("ТЕСТ: FilterDetectionService после исправления декоратора")
    print("=" * 80)

    # Импортируем после инициализации Django
    from filter_detection_service import FilterDetectionService
    from ai_agent_service import AIAgentService

    # Инициализируем AIAgentService (нужен для FilterDetectionService)
    try:
        ai_agent = AIAgentService()
        print("✅ AIAgentService инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации AIAgentService: {e}")
        return False

    # Инициализируем FilterDetectionService
    try:
        filter_service = FilterDetectionService(ai_agent_service=ai_agent)
        print("✅ FilterDetectionService инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации FilterDetectionService: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Проверяем, что справочники загружены
    print(f"\n📊 Загруженные справочники:")
    print(f"   Категорий: {len(filter_service.categories_list)}")
    print(f"   Примеров объектов: {len(filter_service.objects_examples)}")

    if len(filter_service.categories_list) == 0:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: Список категорий пуст!")
        return False

    if len(filter_service.objects_examples) == 0:
        print("❌ КРИТИЧЕСКАЯ ОШИБКА: Список примеров пуст!")
        return False

    # Тестируем загрузку промптов (имитация работы)
    print(f"\n🔍 Тестирование создания промптов...")

    test_txtPrb = "пахнет газом в доме"

    try:
        # Тестируем incident_type промпт
        prompt_incident = await filter_service._create_incident_type_prompt(test_txtPrb)
        if "ТЕХНИЧЕСКАЯ ОШИБКА" in prompt_incident:
            print("❌ incident_type: ИСПОЛЬЗУЕТСЯ FALLBACK-ПРОМПТ!")
            print(f"   Промпт: {prompt_incident[:200]}...")
            return False
        else:
            print("✅ incident_type: Промпт загружен из БД")

        # Тестируем location_type промпт
        prompt_location = await filter_service._create_location_type_prompt(test_txtPrb)
        if "ТЕХНИЧЕСКАЯ ОШИБКА" in prompt_location:
            print("❌ location_type: ИСПОЛЬЗУЕТСЯ FALLBACK-ПРОМПТ!")
            print(f"   Промпт: {prompt_location[:200]}...")
            return False
        else:
            print("✅ location_type: Промпт загружен из БД")

        # Тестируем category промпт
        prompt_category = await filter_service._create_category_prompt(test_txtPrb)
        if "ТЕХНИЧЕСКАЯ ОШИБКА" in prompt_category:
            print("❌ category: ИСПОЛЬЗУЕТСЯ FALLBACK-ПРОМПТ!")
            print(f"   Промпт: {prompt_category[:200]}...")
            return False
        else:
            print("✅ category: Промпт загружен из БД")

    except Exception as e:
        print(f"❌ Ошибка при создании промптов: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    print("=" * 80)
    print("\n📋 Итог:")
    print("   ✅ Декоратор @sync_to_async работает корректно")
    print("   ✅ Промпты загружаются из БД (не fallback)")
    print("   ✅ FilterDetectionService полностью функционален")
    print()

    return True


if __name__ == "__main__":
    # Инициализация Django
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
    django.setup()

    # Запуск теста
    result = asyncio.run(test_filter_detection())

    sys.exit(0 if result else 1)
