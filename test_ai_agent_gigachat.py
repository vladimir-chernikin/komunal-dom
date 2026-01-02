#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки GigaChat API через AIAgentService

Запуск:
    python test_ai_agent_gigachat.py
"""

import asyncio
import sys
from ai_agent_service import AIAgentService


async def test_gigachat():
    """Тестирование вызова GigaChat"""

    print("=" * 80)
    print("ТЕСТИРОВАНИЕ GigaChat API через AIAgentService")
    print("=" * 80)
    print()

    # Инициализация сервиса (по умолчанию теперь GigaChat-2)
    service = AIAgentService()

    print(f"Провайдер по умолчанию: {service.provider}")
    print(f"Модель по умолчанию: {service.default_model}")
    print(f"GigaChat доступен: {service.gigachat_available}")
    print()

    if not service.gigachat_available:
        print("ОШИБКА: GigaChat недоступен! Проверьте credentials в .env")
        return False

    # ТЕСТ 1: Простой запрос
    print("-" * 80)
    print("ТЕСТ 1: Простой запрос 'Привет! Как дела?'")
    print("-" * 80)

    try:
        response, usage = await service.call_llm(
            "Привет! Как дела? Ответь кратко на русском.",
            provider="gigachat",
            model="GigaChat-2"
        )

        print(f"Ответ: {response}")
        print(f"Токенов: {usage['total_tokens']} (вход: {usage['prompt_tokens']}, выход: {usage['completion_tokens']})")
        print(f"Стоимость: {usage['cost_rub']} руб.")
        print()

    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ТЕСТ 2: Запрос с JSON форматом
    print("-" * 80)
    print("ТЕСТ 2: Запрос с JSON форматом")
    print("-" * 80)

    try:
        response, usage = await service.call_llm(
            """Назови 3 города России. Ответ в формате JSON:
{
  "cities": ["город1", "город2", "город3"]
}""",
            provider="gigachat",
            model="GigaChat-2"
        )

        print(f"Ответ: {response}")
        print(f"Токенов: {usage['total_tokens']}")
        print(f"Стоимость: {usage['cost_rub']} руб.")
        print()

    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    # ТЕСТ 3: Проверка кеширования токена
    print("-" * 80)
    print("ТЕСТ 3: Повторный запрос (проверка кеширования токена)")
    print("-" * 80)

    try:
        response2, usage2 = await service.call_llm(
            "Сколько будет 2+2? Ответь одной цифрой.",
            provider="gigachat",
            model="GigaChat-2"
        )

        print(f"Ответ: {response2}")
        print(f"Токенов: {usage2['total_tokens']}")
        print(f"Стоимость: {usage2['cost_rub']} руб.")
        print()

    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Статистика
    print("=" * 80)
    print("СТАТИСТИКА ИСПОЛЬЗОВАНИЯ")
    print("=" * 80)
    stats = service.get_statistics()
    print(f"Всего запросов: {stats['total_requests']}")
    print(f"Всего токенов: {stats['total_tokens']}")
    print(f"Общая стоимость: {stats['total_cost_rub']} руб.")
    print(f"GigaChat запросов: {stats['gigachat']['requests']}")
    print(f"GigaChat токенов: {stats['gigachat']['tokens']}")
    print(f"GigaChat стоимость: {stats['gigachat']['cost_rub']} руб.")
    print()

    print("=" * 80)
    print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print("=" * 80)

    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_gigachat())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\nКРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
