"""
Тестовый скрипт для GigaChat Service

Дата создания: 2025-12-28
Назначение: Проверка работы GigaChat с реальным диалогом

Использование:
    python test_gigachat.py                    # Тест базовой функциональности
    python test_gigachat.py --model GigaChat-2 # Тест конкретной модели
    python test_gigachat.py --dialog           # Тест на реальном диалоге
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime

# Добавляем текущую директорию в path
sys.path.insert(0, '/var/www/komunal-dom_ru')

from gigachat_service import GigaChatService, GigaChatModel

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Реальный диалог из Telegram (Vladimir Chernikin ↔ KomunalkaBot)
TEST_DIALOG = [
    {
        "role": "user",
        "text": "привет",
        "expected": "Приветствие"
    },
    {
        "role": "assistant",
        "text": "Здравствуйте! Опишите вашу проблему, и я попробую помочь.",
        "expected": "Ответ на приветствие"
    },
    {
        "role": "user",
        "text": "у меня течет",
        "expected": "Проблема: течет"
    },
    {
        "role": "assistant",
        "text": "Опишите подробнее, что течёт?",
        "expected": "Уточнение: что течет"
    },
    {
        "role": "user",
        "text": "труба",
        "expected": "Объект: труба"
    },
    {
        "role": "assistant",
        "text": "Опишите подробнее, что именно с трубой?",
        "expected": "Уточнение: что с трубой"
    },
    {
        "role": "user",
        "text": "течет",
        "expected": "Повтор: течет"
    },
    {
        "role": "assistant",
        "text": "Опишите подробнее, какие последствия у этой проблемы?",
        "expected": "Уточнение: последствия"
    },
    {
        "role": "user",
        "text": "вода",
        "expected": "Последствие: вода"
    },
    {
        "role": "assistant",
        "text": "Где течёт труба?",
        "expected": "Уточнение: локация"
    },
    {
        "role": "user",
        "text": "в зале",
        "expected": "Локация: зал"
    },
    {
        "role": "assistant",
        "text": "Какой объект прорвало или где именно течёт труба?",
        "expected": "Уточнение: точная локация"
    },
    {
        "role": "user",
        "text": "у батареи",
        "expected": "Детализация: у батареи"
    },
    {
        "role": "assistant",
        "text": "Какой характер у течи: капли, струйка, поток?",
        "expected": "Уточнение: характер течи"
    },
    {
        "role": "user",
        "text": "тебе не похер?",
        "expected": "Недовольство пользователя"
    }
]


async def test_models_info():
    """Тест 1: Вывод информации о доступных моделях"""
    print("\n" + "="*80)
    print("ТЕСТ 1: Информация о моделях GigaChat")
    print("="*80)

    models = GigaChatModel.get_all_models()

    for model_name, model_info in models.items():
        print(f"\n📊 {model_name}")
        print(f"   Описание: {model_info['description']}")
        print(f"   Стоимость: {model_info['cost_per_1k_tokens']} руб./1000 токенов")
        print(f"   Контекст: {model_info['context_length']} токенов")
        print(f"   Применение: {model_info['use_case']}")

    # Рекомендации
    print("\n" + "-"*80)
    print("РЕКОМЕНДАЦИИ ПО ВЫБОРУ МОДЕЛИ:")
    print("-"*80)
    print(f"  Простые задачи: {GigaChatModel.recommend_model('simple')}")
    print(f"  Средние задачи: {GigaChatModel.recommend_model('medium')}")
    print(f"  Сложные задачи: {GigaChatModel.recommend_model('complex')}")


async def test_oauth_token():
    """Тест 2: Получение OAuth токена"""
    print("\n" + "="*80)
    print("ТЕСТ 2: Получение OAuth токена")
    print("="*80)

    service = GigaChatService(model="GigaChat")

    try:
        token = await service._get_access_token()
        print(f"\n✅ OAuth токен получен успешно!")
        print(f"   Токен (первые 20 символов): {token[:20]}...")
        print(f"   Истекает: {service._token_expires_at}")

        return True
    except Exception as e:
        print(f"\n❌ Ошибка при получении токена: {e}")
        return False
    finally:
        await service.close()


async def test_simple_analyze(model: str = "GigaChat"):
    """Тест 3: Простой анализ сообщения"""
    print("\n" + "="*80)
    print(f"ТЕСТ 3: Анализ сообщения (модель: {model})")
    print("="*80)

    service = GigaChatService(model=model)

    try:
        message = "у меня течет труба в зале"
        print(f"\n📝 Сообщение: '{message}'")

        result, usage = await service.analyze_message(message, task="simple")

        print(f"\n📊 Результат анализа:")
        print(result)
        print(f"\n💰 Стоимость: {usage['cost_rub']} руб.")
        print(f"   Токенов: {usage['total_tokens']} (in: {usage['prompt_tokens']}, out: {usage['completion_tokens']})")

        return True
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await service.close()


async def test_dialog_simulation(model: str = "GigaChat"):
    """Тест 4: Симуляция диалога с накоплением контекста"""
    print("\n" + "="*80)
    print(f"ТЕСТ 4: Симуляция диалога (модель: {model})")
    print("="*80)

    service = GigaChatService(model=model)

    try:
        # Извлекаем только сообщения пользователя
        user_messages = [m for m in TEST_DIALOG if m["role"] == "user"]

        print(f"\n📋 Всего сообщений пользователя: {len(user_messages)}\n")

        total_cost = 0
        total_tokens = 0

        for i, msg in enumerate(user_messages, 1):
            print(f"\n{'─'*80}")
            print(f"Сообщение #{i}: {msg['text']}")
            print(f"{'─'*80}")

            # Анализируем сообщение
            result, usage = await service.analyze_message(msg['text'], task="medium")

            total_cost += usage['cost_rub']
            total_tokens += usage['total_tokens']

            print(f"\nРезультат анализа:")
            print(result)
            print(f"\nСтоимость: {usage['cost_rub']} руб., Токенов: {usage['total_tokens']}")

            # Небольшая пауза между запросами
            await asyncio.sleep(0.5)

        print(f"\n\n{'='*80}")
        print(f"ИТОГИ ДИАЛОГА:")
        print(f"{'='*80}")
        print(f"   Обработано сообщений: {len(user_messages)}")
        print(f"   Всего токенов: {total_tokens}")
        print(f"   Общая стоимость: {total_cost:.4f} руб.")
        print(f"   Средняя стоимость сообщения: {total_cost/len(user_messages):.4f} руб.")

        return True
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await service.close()


async def test_smart_clarification(model: str = "GigaChat"):
    """Тест 5: Умная генерация уточняющих вопросов"""
    print("\n" + "="*80)
    print(f"ТЕСТ 5: Умная генерация уточнений (модель: {model})")
    print("="*80)

    service = GigaChatService(model=model)

    try:
        # Контекст после 3-х сообщений
        context = {
            "txtPrb": "у пользователя течет",
            "known_info": {
                "problem": "течет",
                "location": None,
                "object": None
            },
            "candidates": [
                {"service_id": 7, "service_name": "Устранение течи", "confidence": 0.75},
                {"service_id": 25, "service_name": "Прорыв труб в квартире", "confidence": 0.65}
            ]
        }

        print(f"\n📋 Контекст:")
        print(f"   txtPrb: {context['txtPrb']}")
        print(f"   Известно: {context['known_info']}")
        print(f"   Кандидатов услуг: {len(context['candidates'])}")

        question, usage = await service.generate_clarification_question(context)

        print(f"\n❓ Сгенерированный вопрос:")
        print(f"   {question}")
        print(f"\n💰 Стоимость: {usage['cost_rub']} руб.")

        return True
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await service.close()


async def main():
    """Главная функция запуска тестов"""
    parser = argparse.ArgumentParser(description="Тестирование GigaChat Service")
    parser.add_argument("--model", default="GigaChat", help="Модель GigaChat (по умолчанию: GigaChat)")
    parser.add_argument("--dialog", action="store_true", help="Запустить тест на реальном диалоге")
    parser.add_argument("--all", action="store_true", help="Запустить все тесты")

    args = parser.parse_args()

    print("\n" + "="*80)
    print(" GIGACHAT SERVICE - ТЕСТИРОВАНИЕ")
    print("="*80)
    print(f" Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Модель: {args.model}")
    print("="*80)

    try:
        if args.all:
            # Запускаем все тесты
            await test_models_info()
            await test_oauth_token()
            await test_simple_analyze(args.model)
            await test_smart_clarification(args.model)
            await test_dialog_simulation(args.model)
        elif args.dialog:
            # Только симуляция диалога
            await test_dialog_simulation(args.model)
        else:
            # Базовые тесты
            await test_models_info()
            await test_oauth_token()
            await test_simple_analyze(args.model)

        print("\n" + "="*80)
        print(" ✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
        print("="*80)

    except KeyboardInterrupt:
        print("\n\n⚠️  Тесты прерваны пользователем")
    except Exception as e:
        print(f"\n\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
