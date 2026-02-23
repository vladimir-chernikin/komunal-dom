#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки Yandex Embeddings API
"""

import asyncio
import sys
import os
sys.path.append('/var/www/komunal-dom_ru')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from ai_agent_service import AIAgentService

async def test_embeddings():
    """Тестируем Yandex Embeddings API"""

    print("=" * 60)
    print("ТЕСТ YANDEX EMBEDDINGS API")
    print("=" * 60)

    # Создаем сервис
    service = AIAgentService(provider='yandexgpt')

    print(f"\n1. Проверка доступности:")
    print(f"   YandexGPT доступен: {service.yandexgpt_available}")
    print(f"   API Key: {service.yandexgpt_api_key[:20]}...{service.yandexgpt_api_key[-10:]}")
    print(f"   Folder ID: {service.yandexgpt_folder_id}")

    # Текст для теста
    test_text = "прорыв канализации в ванной комнате"

    print(f"\n2. Текст для векторизации:")
    print(f"   '{test_text}'")

    try:
        print(f"\n3. Вызов Yandex Embeddings API...")

        embedding, usage = await service.get_embedding(test_text)

        print(f"\n4. РЕЗУЛЬТАТ:")
        print(f"   Размерность вектора: {len(embedding)}")
        print(f"   Первые 10 значений: {embedding[:10]}")
        print(f"   Длина текста: {usage['text_length']} символов")
        print(f"   Стоимость: {usage['cost_rub']:.6f} руб.")
        print(f"   Модель: {usage['model']}")

        print(f"\n5. Статистика:")
        print(f"   Requests: {service.stats['embeddings']['requests']}")
        print(f"   Tokens: {service.stats['embeddings']['tokens']}")
        print(f"   Cost: {service.stats['embeddings']['cost']:.6f} руб.")

        print(f"\n✅ УСПЕХ! Yandex Embeddings API работает!")

        return embedding, usage

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return None, None

if __name__ == "__main__":
    asyncio.run(test_embeddings())
