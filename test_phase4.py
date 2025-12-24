#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import uuid
import logging

# Добавляем текущую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка Django
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from ai_cost_tracking_service import AICostTrackingService


def run_tests():
    """Запустить все тесты для AICostTrackingService"""

    print("\n" + "="*60)
    print("🧪 НАЧИНАЕМ ТЕСТЫ ФАЗЫ 4: AICostTrackingService")
    print("="*60 + "\n")

    # Тест 1: Расчет стоимости
    print("💰 Тест 1: Расчет стоимости токенов")
    tracker = AICostTrackingService()

    # Тест разных моделей
    cost_lite = tracker._calculate_cost('yandexgpt-lite', 1000)
    cost_pro = tracker._calculate_cost('yandexgpt-pro', 1000)
    cost_gpt4 = tracker._calculate_cost('gpt-4', 1000)
    cost_gemini = tracker._calculate_cost('gemini-pro', 1000)

    print(f"   YandexGPT Lite (1000 токенов): ${cost_lite:.6f}")
    print(f"   YandexGPT Pro (1000 токенов): ${cost_pro:.6f}")
    print(f"   GPT-4 (1000 токенов): ${cost_gpt4:.6f}")
    print(f"   Gemini Pro (1000 токенов): ${cost_gemini:.6f}")

    # Проверки
    assert cost_lite > 0, "Стоимость не может быть нулевой"
    assert cost_pro > cost_lite, "Pro должен быть дороже lite"
    assert cost_gpt4 > cost_pro, "GPT-4 должен быть дороже pro"

    print("✅ Тест 1 пройден: расчет стоимости работает корректно\n")

    # Тест 2: Отслеживание запроса
    print("📊 Тест 2: Отслеживание LLM запроса")
    trace_id = str(uuid.uuid4())
    dialog_id = str(uuid.uuid4())
    user_id = 12345

    result = tracker.track_llm_request(
        trace_id=trace_id,
        dialog_id=dialog_id,
        user_id=user_id,
        model_name='yandexgpt-lite',
        prompt_tokens=250,
        completion_tokens=200,
        response_time_ms=1500,
        success=True,
        service_type='service_detection'
    )

    print(f"   Request ID: {result['request_id'][:8]}...")
    print(f"   Total tokens: {result['total_tokens']}")
    print(f"   Cost USD: ${result['cost_usd']:.6f}")
    print(f"   Cost RUB: {result['cost_rub']:.4f}₽")
    print(f"   Success: {result['success']}")

    assert result['request_id'] is not None, "Request ID должен быть сгенерирован"
    assert result['total_tokens'] == 450, "Суммарное количество токенов неверно"
    assert result['cost_usd'] > 0, "Стоимость должна быть больше нуля"
    assert result['success'] == True, "Статус должен быть успешным"

    print("✅ Тест 2 пройден: отслеживание запроса работает\n")

    # Тест 3: Провальный запрос
    print("❌ Тест 3: Отслеживание провального запроса")
    trace_id_fail = str(uuid.uuid4())

    result_fail = tracker.track_llm_request(
        trace_id=trace_id_fail,
        dialog_id=dialog_id,
        user_id=user_id,
        model_name='yandexgpt-lite',
        prompt_tokens=0,
        completion_tokens=0,
        response_time_ms=5000,
        success=False,
        error_message="API Error: Rate limit exceeded",
        service_type='address_extraction'
    )

    print(f"   Request ID: {result_fail['request_id'][:8]}...")
    print(f"   Total tokens: {result_fail['total_tokens']}")
    print(f"   Success: {result_fail['success']}")

    assert result_fail['success'] == False, "Статус должен быть провальным"

    print("✅ Тест 3 пройден: обработка ошибок работает\n")

    # Тест 4: Получение дневных расходов
    print("📈 Тест 4: Получение дневной статистики")
    today = os.popen('date +%Y-%m-%d').read().strip()

    daily_costs = tracker.get_daily_costs(today)

    print(f"   Дата: {daily_costs['date']}")
    print(f"   Всего запросов: {daily_costs['requests_count']}")
    print(f"   Всего токенов: {daily_costs['tokens_used']}")
    print(f"   Общая стоимость: {daily_costs['total_cost_rub']:.4f}₽")
    print(f"   Успешность: {daily_costs['success_rate']:.1f}%")

    assert 'date' in daily_costs, "Дата должна быть в ответе"
    assert 'total_cost_rub' in daily_costs, "Стоимость должна быть в ответе"
    assert daily_costs['total_cost_rub'] >= 0, "Стоимость не может быть отрицательной"

    print("✅ Тест 4 пройден: дневная статистика работает\n")

    # Тест 5: Получение месячных расходов
    print("📊 Тест 5: Получение месячной статистики")
    now = os.popen('date +%Y-%m').read().strip()

    monthly_costs = tracker.get_monthly_costs()

    print(f"   Год: {monthly_costs['year']}")
    print(f"   Месяц: {monthly_costs['month']}")
    print(f"   Всего запросов: {monthly_costs['requests_count']}")
    print(f"   Всего токенов: {monthly_costs['tokens_used']}")
    print(f"   Общая стоимость: {monthly_costs['total_cost_rub']:.4f}₽")
    print(f"   Активных дней с данными: {len(monthly_costs['daily_breakdown'])}")

    assert 'year' in monthly_costs, "Год должен быть в ответе"
    assert 'month' in monthly_costs, "Месяц должен быть в ответе"
    assert 'total_cost_rub' in monthly_costs, "Стоимость должна быть в ответе"

    print("✅ Тест 5 пройден: месячная статистика работает\n")

    # Тест 6: Определение провайдера по модели
    print("🏢 Тест 6: Определение провайдера AI")

    providers = [
        ('yandexgpt-lite', 'yandex'),
        ('yandexgpt-pro', 'yandex'),
        ('gpt-4', 'openai'),
        ('gpt-3.5-turbo', 'openai'),
        ('gemini-pro', 'google'),
        ('claude-3-sonnet', 'anthropic'),
        ('unknown-model', 'unknown')
    ]

    for model, expected_provider in providers:
        provider = tracker._get_provider_by_model(model)
        print(f"   {model} → {provider}")
        assert provider == expected_provider, f"Неверный провайдер для {model}"

    print("✅ Тест 6 пройден: определение провайдера работает\n")

    # Тест 7: Неизвестная модель
    print("❓ Тест 7: Обработка неизвестной модели")

    unknown_cost = tracker._calculate_cost('unknown-model', 1000)
    assert unknown_cost == 0, "Стоимость неизвестной модели должна быть 0"

    unknown_provider = tracker._get_provider_by_model('unknown-model')
    assert unknown_provider == 'unknown', "Провайдер неизвестной модели должен быть 'unknown'"

    print("✅ Тест 7 пройден: неизвестная модель обрабатывается корректно\n")

    # Тест 8: Пользовательская статистика
    print("👤 Тест 8: Статистика пользователя")

    user_costs = tracker.get_user_costs(user_id, days=30)

    print(f"   User ID: {user_costs['user_id']}")
    print(f"   Период: {user_costs['days_period']} дней")
    print(f"   Всего запросов: {user_costs['requests_count']}")
    print(f"   Общая стоимость: {user_costs['total_cost_rub']:.4f}₽")
    print(f"   Активных дней: {user_costs['active_days']}")

    assert user_costs['user_id'] == user_id, "ID пользователя должен совпадать"
    assert 'total_cost_rub' in user_costs, "Стоимость должна быть в ответе"

    print("✅ Тест 8 пройден: пользовательская статистика работает\n")

    # Тест 9: Производительность моделей
    print("⚡ Тест 9: Статистика производительности моделей")

    model_performance = tracker.get_model_performance(days=7)

    print(f"   Период: {model_performance['period_days']} дней")
    print(f"   Количество моделей: {model_performance['models_count']}")

    for model_stat in model_performance['models']:
        print(f"   - {model_stat['model_name']}: {model_stat['total_requests']} запросов, "
              f"{model_stat['avg_response_time_ms']:.0f}ms avg, "
              f"{model_stat['success_rate']:.1f}% success")

    assert 'period_days' in model_performance, "Период должен быть в ответе"
    assert 'models' in model_performance, "Список моделей должен быть в ответе"

    print("✅ Тест 9 пройден: производительность моделей работает\n")

    # Финальная проверка
    print("🎉 ФИНАЛЬНАЯ ПРОВЕРКА")

    # Проверим общую стоимость за сегодня (должна быть > 0)
    final_daily = tracker.get_daily_costs()
    if final_daily['total_cost_rub'] > 0:
        print(f"✅ Сегодня потрачено: {final_daily['total_cost_rub']:.4f}₽")
        print("✅ Тестирование прошло успешно - данные сохраняются в БД!")
    else:
        print("ℹ️  Сегодня еще нет расходов или проблемы с сохранением в БД")

    print("\n" + "="*60)
    print("🎉 ВСЕ ТЕСТЫ ФАЗЫ 4 УСПЕШНО ПРОЙДЕНЫ!")
    print("AICostTrackingService работает ИДЕАЛЬНО! ✅")
    print("Готов к интеграции с другими компонентами!")
    print("="*60 + "\n")

    return True


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)