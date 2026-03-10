#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование системы обнаружения услуг
"""

import os
import sys

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from service_detection_orchestrator import ServiceDetectionOrchestrator

def test_service_detection():
    """Тестируем систему обнаружения услуг"""

    print("🧪 Тестирование системы обнаружения услуг...")

    try:
        # Инициализируем оркестратор
        orchestrator = ServiceDetectionOrchestrator()
        print("✅ Оркестратор успешно инициализирован")

        # Тестовые сообщения
        test_messages = [
            "Протекает кран на кухне",
            "Забилась раковина в ванной",
            "Нет света в квартире",
            "Перегорела лампочка",
            "Из потолка капает вода",
            "Не работает розетка",
            "Лифт не едет",
            "Прорвало батарею отопления",
            "Повредили входную дверь",
            "Нет отопления в квартире"
        ]

        for i, message in enumerate(test_messages, 1):
            print(f"\n--- Тест {i}: '{message}' ---")

            result = orchestrator.process_message(
                message_text=message,
                telegram_user_id=12345,
                telegram_username="test_user",
                dialog_id=f"test_dialog_{i}"
            )

            print(f"Статус: {result['status']}")

            if result['status'] == 'PENDING_CONFIRMATION':
                print(f"Услуга: {result.get('message', '')}")
            elif result['status'] == 'NEED_ADDRESS':
                service_name = orchestrator._get_service_name(result['service_id'])
                print(f"Определена услуга: {service_name}")
                print("Требуется адрес")
            elif result['status'] == 'REJECTED_SPAM':
                print("Сообщение отклонено как спам")
            else:
                print(f"Результат: {result}")

        print("\n🎉 Тестирование завершено!")

    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()

def test_address_extraction():
    """Тестируем извлечение адресов"""

    print("\n🧪 Тестирование извлечения адресов...")

    try:
        from service_detection_modules import AddressExtractor

        extractor = AddressExtractor()

        test_addresses = [
            "ул. Ленина, д. 5, кв. 10",
            "г. Москва, ул. Тверская, д. 1",
            "Проспект Мира, дом 25, квартира 15",
            "Адрес: ул. Советская, д. 10, кв. 5"
        ]

        for address in test_addresses:
            print(f"\nАдрес: '{address}'")
            components = extractor.extract_address_components(address)
            print(f"Компоненты: {components}")

            # Проверяем валидацию
            if components.get('street') and components.get('house_number'):
                validation = extractor.validate_and_match_to_db(components)
                print(f"Валидация: {validation}")

    except Exception as e:
        print(f"❌ Ошибка при тестировании адресов: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_service_detection()
    test_address_extraction()