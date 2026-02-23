#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование исправления поиска услуги "Нет горячей воды"

Сценарий:
1. Пользователь: "нет вод"
2. Бот: "Какой воды — горячей или холодной?"
3. Пользователь: "горячей"
4. Бот: Создает заявку на "Нет горячей воды во всём доме"

Дата: 2026-02-18
"""

import asyncio
import sys
sys.path.append('/var/www/komunal-dom_ru')

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from main_agent import MainAgent
from semantic_search_service import SemanticSearchService
from tag_search_service import TagSearchService
from vector_search_service import VectorSearchService


async def test_water_service():
    """Тестируем полный сценарий поиска услуги "Нет горячей воды" """

    print("=" * 80)
    print("ТЕСТ: Сценарий 'нет вод' → 'горячей' → 'Нет горячей воды во всём доме'")
    print("=" * 80)

    # Инициализация сервисов
    main_agent = MainAgent()

    # Шаг 1: Первое сообщение "нет вод"
    print("\n" + "=" * 80)
    print("ШАГ 1: Пользователь пишет 'нет вод'")
    print("=" * 80)

    session_id = "test_water_service_fix"

    response_1 = await main_agent.process_service_detection(
        message_text="нет вод",
        user_context={
            'session_id': session_id,
            'channel': 'web',
            'user_id': 'test_user'
        }
    )

    print(f"\nСтатус: {response_1.get('status')}")
    print(f"Сообщение: {response_1.get('message', 'N/A')[:200]}")
    print(f"Service ID: {response_1.get('service_id', 'N/A')}")
    print(f"Service Name: {response_1.get('service_name', 'N/A')}")

    # Шаг 2: Второе сообщение "горячей"
    print("\n" + "=" * 80)
    print("ШАГ 2: Пользователь отвечает 'горячей'")
    print("=" * 80)

    response_2 = await main_agent.process_service_detection(
        message_text="горячей",
        user_context={
            'session_id': session_id,
            'channel': 'web',
            'user_id': 'test_user'
        }
    )

    print(f"\nСтатус: {response_2.get('status')}")
    print(f"Сообщение: {response_2.get('message', 'N/A')[:200]}")
    print(f"Service ID: {response_2.get('service_id', 'N/A')}")
    print(f"Service Name: {response_2.get('service_name', 'N/A')}")

    # Проверяем результат
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТ ТЕСТА:")
    print("=" * 80)

    status = response_2.get('status')

    if status == 'SUCCESS':
        service_id = response_2.get('service_id')
        service_name = response_2.get('service_name')
        # confidence может быть в разных полях
        confidence = response_2.get('confidence') or response_2.get('metadata', {}).get('confidence', 'N/A')

        print(f"✅ УСПЕХ: Услуга определена!")
        print(f"   Service ID: {service_id}")
        print(f"   Service Name: {service_name}")
        print(f"   Confidence: {confidence:.1f}%")

        # Проверяем что это правильная услуга
        if service_id == 34 or "Нет горячей воды" in service_name:
            print(f"\n✅ ✅ ✅ ПРАВИЛЬНАЯ УСЛУГА: 'Нет горячей воды во всём доме'")
            print(f"\nИСПРАВЛЕНИЕ УСПЕШНО! Проблема решена!")
            return True
        else:
            print(f"\n❌ НЕПРАВИЛЬНАЯ УСЛУГА: {service_name}")
            print(f"   Ожидалось: 'Нет горячей воды во всём доме' (ID 34)")
            return False
    else:
        print(f"❌ ПРОВАЛ: Услуга НЕ определена")
        print(f"   Статус: {status}")
        print(f"   Сообщение: {response_2.get('message', 'N/A')[:200]}")
        return False


if __name__ == "__main__":
    result = asyncio.run(test_water_service())

    print("\n" + "=" * 80)
    if result:
        print("ИТОГ: ✅ ТЕСТ ПРОЙДЕН УСПЕШНО")
    else:
        print("ИТОГ: ❌ ТЕСТ ПРОВАЛЕН")
    print("=" * 80)
