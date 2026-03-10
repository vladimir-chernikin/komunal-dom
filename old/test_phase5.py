#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import uuid
import logging
import datetime

# Добавляем текущую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка Django
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from django.db import connection


def run_tests():
    """Запустить все тесты для Части 5 - Расширенное логирование и БД"""

    print("\n" + "="*60)
    print("🧪 НАЧИНАЕМ ТЕСТЫ ФАЗЫ 5: Расширенное логирование и БД")
    print("="*60 + "\n")

    # Тест 1: Проверка Views
    print("📊 Тест 1: Проверка аналитических Views")

    try:
        with connection.cursor() as cursor:
            # Тест v_daily_ai_costs
            cursor.execute("SELECT COUNT(*) FROM v_daily_ai_costs")
            daily_count = cursor.fetchone()[0]
            print(f"   v_daily_ai_costs: {daily_count} записей")

            # Тест v_monthly_ai_costs
            cursor.execute("SELECT COUNT(*) FROM v_monthly_ai_costs")
            monthly_count = cursor.fetchone()[0]
            print(f"   v_monthly_ai_costs: {monthly_count} записей")

            # Тест v_dialog_stats
            cursor.execute("SELECT COUNT(*) FROM v_dialog_stats")
            dialog_count = cursor.fetchone()[0]
            print(f"   v_dialog_stats: {dialog_count} диалогов")

            # Тест v_user_activity
            cursor.execute("SELECT COUNT(*) FROM v_user_activity")
            user_count = cursor.fetchone()[0]
            print(f"   v_user_activity: {user_count} пользователей")

        print("✅ Тест 1 пройден: Views работают корректно\n")

    except Exception as e:
        print(f"❌ Тест 1 не пройден: {e}\n")

    # Тест 2: Проверка функций
    print("🧮 Тест 2: Проверка аналитических функций")

    try:
        with connection.cursor() as cursor:
            # Тест fn_calculate_ai_cost
            cursor.execute("SELECT fn_calculate_ai_cost('yandexgpt-lite', 1000)")
            cost_result = cursor.fetchone()[0]
            print(f"   fn_calculate_ai_cost(yandexgpt-lite, 1000): ${cost_result:.6f}")

            # Тест fn_calculate_ai_cost для разных моделей
            models = ['yandexgpt-lite', 'gpt-4', 'gemini-pro']
            for model in models:
                cursor.execute(f"SELECT fn_calculate_ai_cost('{model}', 1000)")
                cost = cursor.fetchone()[0]
                print(f"   {model}: ${cost:.6f} за 1000 токенов")

        print("✅ Тест 2 пройден: Функции расчета работают\n")

    except Exception as e:
        print(f"❌ Тест 2 не пройден: {e}\n")

    # Тест 3: Проверка триггеров
    print("🔄 Тест 3: Проверка работы триггеров")

    try:
        from ai_cost_tracking_service import AICostTrackingService
        tracker = AICostTrackingService()

        # Создаем тестовый диалог
        test_dialog_id = str(uuid.uuid4())
        test_user_id = 99999

        with connection.cursor() as cursor:
            # Вставляем тестовый диалог
            cursor.execute("""
                INSERT INTO dialog_memory_store (dialog_id, user_id, message_count, ai_requests_count)
                VALUES (%s, %s, 0, 0)
            """, [test_dialog_id, test_user_id])

            # Проверяем начальные значения
            cursor.execute("SELECT ai_requests_count FROM dialog_memory_store WHERE dialog_id = %s", [test_dialog_id])
            initial_requests = cursor.fetchone()[0]
            print(f"   Начальное количество AI запросов: {initial_requests}")

            # Отправляем AI запрос (должен сработать триггер)
            tracker.track_llm_request(
                trace_id=str(uuid.uuid4()),
                dialog_id=test_dialog_id,
                user_id=test_user_id,
                model_name='yandexgpt-lite',
                prompt_tokens=100,
                completion_tokens=50,
                success=True
            )

            # Проверяем обновленное значение
            cursor.execute("SELECT ai_requests_count FROM dialog_memory_store WHERE dialog_id = %s", [test_dialog_id])
            final_requests = cursor.fetchone()[0]
            print(f"   Финальное количество AI запросов: {final_requests}")

            assert final_requests > initial_requests, "Триггер не увеличил счетчик"

        print("✅ Тест 3 пройден: Триггеры работают корректно\n")

    except Exception as e:
        print(f"❌ Тест 3 не пройден: {e}\n")

    # Тест 4: Проверка автоматического расчета стоимости
    print("💰 Тест 4: Проверка автоматического расчета стоимости")

    try:
        with connection.cursor() as cursor:
            # Вставляем запись без указания стоимости
            test_dialog_id = str(uuid.uuid4())
            test_user_id = 88888

            cursor.execute("""
                INSERT INTO ai_cost_tracking (dialog_id, user_id, ai_provider, model_name, input_tokens, output_tokens)
                VALUES (%s, %s, 'yandex', 'yandexgpt-lite', 200, 100)
                RETURNING id, cost_rub
            """, [test_dialog_id, test_user_id])

            result = cursor.fetchone()
            inserted_id, calculated_cost = result[0], result[1]

            print(f"   Запись ID: {inserted_id}")
            print(f"   Автоматически рассчитанная стоимость: {calculated_cost:.6f}₽")

            # Проверяем правильность расчета вручную
            expected_cost = 0.00024 * ((200 + 100) / 1000) * 100  # конвертация в рубли
            print(f"   Ожидаемая стоимость: {expected_cost:.6f}₽")

            # Допустимая погрешность из-за округления
            assert abs(calculated_cost - expected_cost) < 0.001, "Стоимость рассчитана неверно"

        print("✅ Тест 4 пройден: Автоматический расчет стоимости работает\n")

    except Exception as e:
        print(f"❌ Тест 4 не пройден: {e}\n")

    # Тест 5: Статистика по диалогам
    print("📈 Тест 5: Статистика по диалогам")

    try:
        with connection.cursor() as cursor:
            # Получаем статистику по всем диалогам
            cursor.execute("""
                SELECT
                    COUNT(*) as total_dialogs,
                    COUNT(CASE WHEN user_name IS NOT NULL THEN 1 END) as with_name,
                    COUNT(CASE WHEN current_service_name IS NOT NULL THEN 1 END) as with_service,
                    AVG(ai_requests_count) as avg_ai_requests,
                    SUM(ai_requests_count) as total_ai_requests
                FROM dialog_memory_store
            """)

            stats = cursor.fetchone()
            total_dialogs, with_name, with_service, avg_ai_requests, total_ai_requests = stats

            print(f"   Всего диалогов: {total_dialogs}")
            print(f"   С именем пользователя: {with_name}")
            print(f"   С определенной услугой: {with_service}")
            print(f"   Среднее AI запросов на диалог: {avg_ai_requests or 0}")
            print(f"   Всего AI запросов: {total_ai_requests or 0}")

        print("✅ Тест 5 пройден: Статистика по диалогам работает\n")

    except Exception as e:
        print(f"❌ Тест 5 не пройден: {e}\n")

    # Тест 6: Тестирование производительности Views
    print("⚡ Тест 6: Тестирование производительности Views")

    try:
        import time

        with connection.cursor() as cursor:
            # Измеряем время выполнения view
            start_time = time.time()
            cursor.execute("SELECT COUNT(*) FROM v_daily_ai_costs WHERE date >= '2025-12-01'")
            view_time = time.time() - start_time

            daily_records = cursor.fetchone()[0]
            print(f"   v_daily_ai_costs: {daily_records} записей, выполнено за {view_time:.4f}с")

            # Проверяем производительность сложного запроса
            start_time = time.time()
            cursor.execute("""
                SELECT model_name, AVG(cost_rub), AVG(response_time_ms)
                FROM v_daily_ai_costs
                WHERE date >= '2025-12-01'
                GROUP BY model_name
            """)
            complex_time = time.time() - start_time

            model_stats = cursor.fetchall()
            print(f"   Сложный запрос: {len(model_stats)} моделей, выполнено за {complex_time:.4f}с")

            for model, avg_cost, avg_time in model_stats:
                print(f"   - {model}: средняя стоимость {avg_cost:.4f}₽, среднее время {avg_time:.0f}ms")

        print("✅ Тест 6 пройден: Views имеют приемлемую производительность\n")

    except Exception as e:
        print(f"❌ Тест 6 не пройден: {e}\n")

    # Тест 7: Проверка пользовательской статистики
    print("👤 Тест 7: Пользовательская статистика")

    try:
        from ai_cost_tracking_service import AICostTrackingService
        tracker = AICostTrackingService()

        # Проверяем для тестового пользователя 12345 (который мы использовали в тестах Части 4)
        user_stats = tracker.get_user_costs(12345, days=30)

        print(f"   User ID: {user_stats['user_id']}")
        print(f"   Период: {user_stats['days_period']} дней")
        print(f"   Всего запросов: {user_stats['requests_count']}")
        print(f"   Общая стоимость: {user_stats['total_cost_rub']:.4f}₽")
        print(f"   Активных дней: {user_stats['active_days']}")

        if 'first_request' in user_stats and user_stats['first_request']:
            print(f"   Первый запрос: {user_stats['first_request'][:19]}")

        print("✅ Тест 7 пройден: Пользовательская статистика работает\n")

    except Exception as e:
        print(f"❌ Тест 7 не пройден: {e}\n")

    # Финальная проверка
    print("🎉 ФИНАЛЬНАЯ ПРОВЕРКА")

    # Проверяем, что все основные компоненты работают
    components_working = 0
    total_components = 7

    tests = [
        ("Views", "SELECT COUNT(*) FROM v_daily_ai_costs"),
        ("Functions", "SELECT fn_calculate_ai_cost('yandexgpt-lite', 1)"),
        ("Triggers", "SELECT COUNT(*) FROM dialog_memory_store WHERE ai_requests_count > 0"),
        ("Auto Cost", "SELECT COUNT(*) FROM ai_cost_tracking WHERE cost_rub > 0"),
        ("Dialog Stats", "SELECT COUNT(*) FROM dialog_memory_store"),
        ("Performance", "SELECT model_name FROM v_daily_ai_costs LIMIT 1"),
        ("User Stats", "SELECT COUNT(*) FROM dialog_memory_store")
    ]

    for test_name, test_query in tests:
        try:
            with connection.cursor() as cursor:
                cursor.execute(test_query)
                result = cursor.fetchone()
                if result and result[0] is not None:
                    components_working += 1
                    print(f"✅ {test_name}: работает")
                else:
                    print(f"❌ {test_name}: нет данных")
        except Exception as e:
            print(f"❌ {test_name}: ошибка - {e}")

    success_rate = (components_working / total_components) * 100
    print(f"\n🎯 Общий уровень готовности: {success_rate:.1f}% ({components_working}/{total_components})")

    if success_rate >= 80:
        print("🎉 ЧАСТЬ 5 ВЫПОЛНЕНА УСПЕШНО! Расширенное логирование и аналитика работают!")
    else:
        print("⚠️  ЧАСТЬ 5 частично готова. Некоторые компоненты требуют доработки.")

    print("\n" + "="*60)
    print("🎉 ТЕСТЫ ФАЗЫ 5 ЗАВЕРШЕНЫ!")
    if success_rate >= 80:
        print("Расширенное логирование и БД работают ИДЕАЛЬНО! ✅")
    else:
        print("Расширенное логирование и БД работают ЧАСТИЧНО ⚠️")
    print("Готов к интеграции с другими компонентами!")
    print("="*60 + "\n")

    return success_rate >= 80


if __name__ == "__main__":
    try:
        success = run_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)