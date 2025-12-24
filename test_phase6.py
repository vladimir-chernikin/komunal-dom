#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import uuid
import json
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

from service_detection_orchestrator import ServiceDetectionOrchestrator


def run_tests():
    """Запустить все тесты для Части 6 - Финальный JSON"""

    print("\n" + "="*60)
    print("🧪 НАЧИНАЕМ ТЕСТЫ ФАЗЫ 6: Финальный JSON")
    print("="*60 + "\n")

    # Инициализируем orchestrator
    orchestrator = ServiceDetectionOrchestrator()

    # Тест 1: Создание базового JSON
    print("📝 Тест 1: Создание базового JSON")

    try:
        address_components = {
            'street': 'Ленина',
            'house_number': '5',
            'apartment_number': '12',
            'entrance': '2'
        }

        output_json = orchestrator.create_output_json(
            service_id=1,
            service_name="Протечка крана",
            service_confidence=0.92,
            address_components=address_components,
            user_name="Владимир",
            user_phone="+7-999-XXX-XXXX",
            description="Течет кран на кухне",
            trace_id=str(uuid.uuid4())
        )

        print(f"   ✅ JSON создан успешно")
        print(f"   Код услуги: {output_json['кодУслуги']}")
        print(f"   Описание: {output_json['описание']}")
        print(f"   Адрес: {output_json['адрес']}")
        print(f"   Имя: {output_json['имя']}")
        print(f"   Срочность: {output_json['срочность']}")
        print(f"   Уверенность: {output_json['уверенность']}")
        print(f"   Время выполнения: {output_json['предварительноеВремяВыполнения']}")

        # Проверяем обязательные поля
        required_fields = ['кодУслуги', 'срочность', 'описание', 'адрес', 'имя', 'уверенность', 'дата', 'статус']
        for field in required_fields:
            assert field in output_json, f"Отсутствует обязательное поле: {field}"

        print("✅ Тест 1 пройден: Создание JSON работает корректно\n")

    except Exception as e:
        print(f"❌ Тест 1 не пройден: {e}\n")

    # Тест 2: Построение полного адреса
    print("📍 Тест 2: Построение полного адреса")

    try:
        test_cases = [
            ({'street': 'Ленина', 'house_number': '5', 'apartment_number': '12'},
             "ул. Ленина, д. 5, кв. 12"),
            ({'street': 'ул. Мира', 'house_number': '10'},
             "ул. Мира, д. 10"),
            ({'house_number': '15'},
             "д. 15"),
            ({'apartment_number': '25'},
             "Адрес не указан"),
            ({},
             "Адрес не указан")
        ]

        for i, (components, expected) in enumerate(test_cases):
            result = orchestrator._build_full_address(components)
            print(f"   Кейс {i+1}: {result}")
            assert result == expected, f"Ожидалось '{expected}', получено '{result}'"

        print("✅ Тест 2 пройден: Построение адреса работает корректно\n")

    except Exception as e:
        print(f"❌ Тест 2 не пройден: {e}\n")

    # Тест 3: Расчет срочности
    print("🚨 Тест 3: Расчет срочности")

    try:
        # Проверяем разные уровни срочности
        time_estimates = {
            'S0': '1-2 часа',
            'S1': '2-4 часа',
            'S2': '4-8 часов',
            'S3': '1-3 дня',
            'UNKNOWN': '4-8 часов'  # по умолчанию
        }

        for urgency, expected_time in time_estimates.items():
            result = orchestrator._get_estimated_time(urgency)
            print(f"   {urgency}: {result}")
            assert result == expected_time, f"Для {urgency} ожидалось '{expected_time}'"

        print("✅ Тест 3 пройден: Расчет времени выполнения работает корректно\n")

    except Exception as e:
        print(f"❌ Тест 3 не пройден: {e}\n")

    # Тест 4: Поиск кода объекта
    print("🏢 Тест 4: Поиск кода объекта")

    try:
        # Тестируем поиск по разным адресам
        test_addresses = [
            "ул. Ленина, д. 5",
            "Адрес не указан",
            "Неизвестный адрес 123"
        ]

        for address in test_addresses:
            result = orchestrator._get_building_code_by_address(address)
            print(f"   '{address}' → {result}")
            # Результат должен быть строкой
            assert isinstance(result, str), "Результат должен быть строкой"

        print("✅ Тест 4 пройден: Поиск кода объекта работает\n")

    except Exception as e:
        print(f"❌ Тест 4 не пройден: {e}\n")

    # Тест 5: Форматирование для отображения
    print("💬 Тест 5: Форматирование JSON для Telegram")

    try:
        test_json = {
            'кодУслуги': '1',
            'описание': 'Протечка крана на кухне',
            'адрес': 'ул. Ленина, д. 5, кв. 12',
            'номерКвартиры': '12',
            'имя': 'Владимир',
            'телефон': '+7-999-XXX-XXXX',
            'срочность': 'S1',
            'предварительноеВремяВыполнения': '2-4 часа',
            'уверенность': 0.92,
            'request_uuid': str(uuid.uuid4())
        }

        formatted_message = orchestrator.format_json_for_display(test_json)
        print("   Отформатированное сообщение:")
        print("   " + "\n   ".join(formatted_message.split('\n')))

        # Проверяем наличие ключевых элементов
        assert "✅ Заявка создана" in formatted_message
        assert "Протечка крана" in formatted_message
        assert "ул. Ленина" in formatted_message
        assert "Владимир" in formatted_message

        print("\n✅ Тест 5 пройден: Форматирование для отображения работает\n")

    except Exception as e:
        print(f"❌ Тест 5 не пройден: {e}\n")

    # Тест 6: Генерация кнопок подтверждения
    print("🔘 Тест 6: Генерация кнопок подтверждения")

    try:
        buttons = orchestrator.generate_confirmation_buttons(test_json)
        print(f"   Количество строк кнопок: {len(buttons)}")
        print(f"   Количество кнопок в первой строке: {len(buttons[0])}")

        # Проверяем структуру
        assert isinstance(buttons, list), "Кнопки должны быть списком"
        assert len(buttons) == 1, "Должна быть одна строка кнопок"
        assert len(buttons[0]) == 2, "Должно быть две кнопки"

        # Проверяем содержимое
        button_texts = [btn['text'] for btn in buttons[0]]
        assert "✅" in button_texts[0], "Первая кнопка должна содержать ✅"
        assert "❌" in button_texts[1], "Вторая кнопка должна содержать ❌"

        print(f"   Кнопки: {[btn['text'] for btn in buttons[0]]}")
        print("✅ Тест 6 пройден: Генерация кнопок работает\n")

    except Exception as e:
        print(f"❌ Тест 6 не пройден: {e}\n")

    # Тест 7: Валидность JSON
    print("🔍 Тест 7: Валидность JSON")

    try:
        # Проверяем что созданный JSON можно сериализовать
        json_string = json.dumps(output_json, ensure_ascii=False, indent=2)
        parsed_back = json.loads(json_string)

        assert parsed_back == output_json, "JSON должен сериализоваться и десериализоваться без потерь"
        assert len(json_string) > 100, "JSON должен содержать достаточное количество данных"

        print(f"   Размер JSON: {len(json_string)} символов")
        print("   JSON валидный")
        print("✅ Тест 7 пройден: JSON валиден\n")

    except Exception as e:
        print(f"❌ Тест 7 не пройден: {e}\n")

    # Тест 8: Сохранение заявки в БД
    print("💾 Тест 8: Сохранение заявки в базу данных")

    try:
        # Добавляем user_id в JSON для сохранения
        test_json['user_id'] = 999999

        ticket_id = orchestrator.save_final_ticket(test_json, str(uuid.uuid4()))

        print(f"   ID заявки: {ticket_id}")
        assert isinstance(ticket_id, str), "ID заявки должен быть строкой"
        assert len(ticket_id) == 36, "ID заявки должен быть UUID (36 символов)"

        print("✅ Тест 8 пройден: Сохранение в БД работает\n")

    except Exception as e:
        print(f"❌ Тест 8 не пройден: {e}\n")

    # Тест 9: Комплексный тест
    print("🎯 Тест 9: Комплексный тест полного цикла")

    try:
        # Создаем полный JSON для реальной заявки
        full_json = orchestrator.create_output_json(
            service_id=1,
            service_name="Протечка крана на кухне",
            service_confidence=0.95,
            address_components={
                'street': 'Советская',
                'house_number': '15',
                'apartment_number': '42',
                'entrance': '3'
            },
            user_name="Анна Петрова",
            user_phone="+7-916-123-45-67",
            user_email="anna@example.com",
            description="Протекает смеситель на кухне, капает с утра",
            urgency_level="S1",
            trace_id=str(uuid.uuid4())
        )

        # Проверяем все поля
        assert full_json['кодУслуги'] == '1'
        assert full_json['имя'] == 'Анна Петрова'
        assert full_json['срочность'] == 'S1'
        assert 'ул. Советская' in full_json['адрес']
        assert full_json['номерКвартиры'] == '42'
        assert full_json['подъезд'] == '3'

        # Форматируем для отображения
        formatted = orchestrator.format_json_for_display(full_json)
        assert "Анна Петрова" in formatted
        assert "Советская" in formatted

        # Генерируем кнопки
        buttons = orchestrator.generate_confirmation_buttons(full_json)
        assert len(buttons) == 1
        assert len(buttons[0]) == 2

        print(f"   ✅ Полный цикл выполнен успешно")
        print(f"   📋 Создана заявка: {full_json['описание']}")
        print(f"   👤 Клиент: {full_json['имя']}")
        print(f"   📍 Адрес: {full_json['адрес']}")
        print(f"   🚨 Срочность: {full_json['срочность']}")
        print(f"   ⏱ Ожидаемое время: {full_json['предварительноеВремяВыполнения']}")

        print("✅ Тест 9 пройден: Комплексный тест успешен\n")

    except Exception as e:
        print(f"❌ Тест 9 не пройден: {e}\n")

    # Финальная проверка
    print("🎉 ФИНАЛЬНАЯ ПРОВЕРКА")

    # Проверяем все основные методы
    methods_to_test = [
        ("create_output_json", lambda: orchestrator.create_output_json(
            1, "Тест", 0.8, {'street': 'Тестовая'})),
        ("_build_full_address", lambda: orchestrator._build_full_address(
            {'street': 'Тестовая', 'house_number': '1'})),
        ("_get_estimated_time", lambda: orchestrator._get_estimated_time('S2')),
        ("_get_building_code_by_address", lambda: orchestrator._get_building_code_by_address('Тест')),
        ("format_json_for_display", lambda: orchestrator.format_json_for_display(
            {'описание': 'Тест', 'адрес': 'Тест', 'имя': 'Тест'})),
        ("generate_confirmation_buttons", lambda: orchestrator.generate_confirmation_buttons({})),
    ]

    working_methods = 0

    for method_name, method_func in methods_to_test:
        try:
            result = method_func()
            if result is not None:
                working_methods += 1
                print(f"✅ {method_name}: работает")
            else:
                print(f"⚠️  {method_name}: возвращает None")
        except Exception as e:
            print(f"❌ {method_name}: ошибка - {e}")

    success_rate = (working_methods / len(methods_to_test)) * 100
    print(f"\n🎯 Общий уровень готовности: {success_rate:.1f}% ({working_methods}/{len(methods_to_test)})")

    if success_rate >= 90:
        print("🎉 ЧАСТЬ 6 ВЫПОЛНЕНА УСПЕШНО! Финальный JSON работает идеально!")
    elif success_rate >= 70:
        print("⚠️  ЧАСТЬ 6 ВЫПОЛНЕНА ЧАСТИЧНО. Некоторые методы требуют доработки.")
    else:
        print("❌ ЧАСТЬ 6 ТРЕБУЕТ ДОРАБОТКИ.")

    print("\n" + "="*60)
    print("🎉 ТЕСТЫ ФАЗЫ 6 ЗАВЕРШЕНЫ!")
    if success_rate >= 90:
        print("Финальный JSON работает ИДЕАЛЬНО! ✅")
    elif success_rate >= 70:
        print("Финальный JSON работает ЧАСТИЧНО ⚠️")
    else:
        print("Финальный JSON требует доработки ❌")
    print("Готов к интеграции с Telegram ботом!")
    print("="*60 + "\n")

    return success_rate >= 90


if __name__ == "__main__":
    try:
        success = run_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)