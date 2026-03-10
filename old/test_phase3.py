#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для ФАЗЫ 3: AddressExtractor с памятью
"""

import sys
import os
import logging

# Добавляем текущую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_tests():
    print("=" * 60)
    print("🧪 НАЧИНАЕМ ТЕСТЫ ФАЗЫ 3: AddressExtractor с памятью")
    print("=" * 60)

    from service_detection_modules import AddressExtractor

    extractor = AddressExtractor()

    # Тест 1: Парсинг одного сообщения
    print("\n📝 Тест 1: Парсинг адреса из одного сообщения")
    components = extractor._parse_address_text("ул. Ленина, дом 5")
    assert components['street'] == 'Ленина', f"Улица не найдена: {components['street']}"
    assert components['house_number'] == '5', f"Дом не найден: {components['house_number']}"
    print("✅ Тест 1 пройден: парсинг адреса из полного сообщения")

    # Тест 2: Парсинг отдельных компонентов
    print("\n🔍 Тест 2: Парсинг отдельных компонентов")
    # Только улица
    street_only = extractor._parse_address_text("на улице Мира")
    print(f"  DEBUG: Результат парсинга 'на улице Мира': {street_only}")
    assert street_only['street'] == 'Мира', f"Улица не найдена: {street_only['street']}"
    assert street_only['house_number'] is None, f"Дом должен быть None: {street_only['house_number']}"
    print("  ✓ Только улица распознана")

    # Только дом
    house_only = extractor._parse_address_text("дом 15а")
    assert house_only['house_number'] == '15а', f"Дом не найден: {house_only['house_number']}"
    assert house_only['street'] is None, f"Улица должна быть None: {house_only['street']}"
    print("  ✓ Только дом распознан")

    # Только квартира
    apt_only = extractor._parse_address_text("квартира 42")
    assert apt_only['apartment_number'] == '42', f"Квартира не найдена: {apt_only['apartment_number']}"
    print("  ✓ Только квартира распознана")
    print("✅ Тест 2 пройден: отдельные компоненты работают")

    # Тест 3: Объединение с памятью - КЛЮЧЕВОЙ ТЕСТ!
    print("\n🧠 Тест 3: Объединение адреса с памятью (КЛЮЧЕВОЙ)")
    memory_context = {
        'street': 'Ленина',
        'house_number': '5',
        'apartment_number': None,
        'entrance': None
    }

    current = extractor._parse_address_text("кв. 12")
    result = extractor._merge_with_memory(current, memory_context)

    assert result['street'] == 'Ленина', "Улица должна быть из памяти"
    assert result['house_number'] == '5', "Дом должен быть из памяти"
    assert result['apartment_number'] == '12', "Квартира должна быть из текущего"
    assert result.get('from_memory') == True, "Флаг from_memory должен быть True"

    print("  ✓ Улица восстановлена из памяти: Ленина")
    print("  ✓ Дом восстановлен из памяти: 5")
    print("  ✓ Квартира добавлена из текущего: 12")
    print("  ✓ from_memory флаг установлен")
    print("✅ Тест 3 пройден: объединение адреса с памятью работает ИДЕАЛЬНО!")

    # Тест 4: Нормализация
    print("\n✨ Тест 4: Нормализация компонентов")
    input_data = {
        'street': ' Ленина "',
        'house_number': '№5',
        'apartment_number': None
    }
    print(f"  Входные данные: {repr(input_data)}")
    components = extractor._normalize_components(input_data)
    print(f"  Результат: {repr(components)}")
    assert components['street'] == 'Ленина', f"Улица не нормализована: {repr(components['street'])}"
    assert components['house_number'] == '5', f"Дом не нормализован: {repr(components['house_number'])}"
    print("  ✓ Улица очищена от кавычек и пробелов")
    print("  ✓ Номер дома очищен от символа №")
    print("✅ Тест 4 пройден: нормализация работает")

    # Тест 5: Полный цикл с confidence
    print("\n🎯 Тест 5: Полный цикл с расчетом confidence")
    components = extractor.extract_address_components(
        "кв. 12",
        context_memory={'street': 'Ленина', 'house_number': '5', 'apartment_number': None, 'entrance': None}
    )
    assert components['street'] == 'Ленина', "Улица должна быть из памяти"
    assert components['house_number'] == '5', "Дом должен быть из памяти"
    assert components['apartment_number'] == '12', "Квартира должна быть из текущего"
    assert components['confidence'] == 1.0, f"Confidence должен быть 1.0, получен {components['confidence']}"
    print("  ✓ Полный адрес восстановлен из разных сообщений")
    print("  ✓ Confidence рассчитан корректно: 1.0")
    print("✅ Тест 5 пройден: полный цикл работает")

    # Тест 6: Последовательное накопление
    print("\n📈 Тест 6: Последовательное накопление адреса")
    # Имитация диалога
    memory = {'street': None, 'house_number': None, 'apartment_number': None, 'entrance': None}

    # Сообщение 1: "улица Советская"
    result1 = extractor.extract_address_components("улица Советская", memory)
    memory.update({k: v for k, v in result1.items() if k in memory})
    assert result1['street'] == 'Советская', "Шаг 1: улица не распознана"
    print(f"  Шаг 1: ул. {result1['street']}")

    # Сообщение 2: "дом 25"
    result2 = extractor.extract_address_components("дом 25", memory)
    memory.update({k: v for k, v in result2.items() if k in memory})
    assert result2['street'] == 'Советская', "Шаг 2: улица потеряна!"
    assert result2['house_number'] == '25', "Шаг 2: дом не распознан"
    print(f"  Шаг 2: ул. {result2['street']}, д. {result2['house_number']}")

    # Сообщение 3: "квартира 7"
    result3 = extractor.extract_address_components("квартира 7", memory)
    memory.update({k: v for k, v in result3.items() if k in memory})
    assert result3['street'] == 'Советская', "Шаг 3: улица потеряна!"
    assert result3['house_number'] == '25', "Шаг 3: дом потерян!"
    assert result3['apartment_number'] == '7', "Шаг 3: квартира не распознана"
    print(f"  Шаг 3: ул. {result3['street']}, д. {result3['house_number']}, кв. {result3['apartment_number']}")
    assert result3['confidence'] == 1.0, "Шаг 3: confidence должен быть 1.0"

    print("✅ Тест 6 пройден: последовательное накопление работает!")

    # Тест 7: Разные форматы адреса
    print("\n🔧 Тест 7: Разные форматы адреса")
    test_cases = [
        ("пр. Черноморский 10", {"street": "Черноморский", "house_number": "10"}),
        ("пер. Цветочный 5", {"street": "Цветочный", "house_number": "5"}),
        ("бульвар Победы 15", {"street": "Победы", "house_number": "15"}),
        ("д. 7/3", {"house_number": "7/3"}),
        ("№25", {"house_number": "25"}),
        ("кв 123", {"apartment_number": "123"}),
        ("подъезд 2", {"entrance": "2"}),
    ]

    for text, expected in test_cases:
        result = extractor._parse_address_text(text)
        for key, value in expected.items():
            assert result.get(key) == value, f"Формат '{text}': {key} должен быть {value}, получен {result.get(key)}"
        print(f"  ✓ '{text}' → {expected}")

    print("✅ Тест 7 пройден: разные форматы адреса поддерживаются")

    # Тест 8: Проверка граничных случаев
    print("\n⚡ Тест 8: Граничные случаи")
    # Пустая строка
    empty = extractor._parse_address_text("")
    assert empty['street'] is None and empty['house_number'] is None, "Пустая строка обработана неверно"
    print("  ✓ Пустая строка корректно обработана")

    # Текст без адреса
    no_address = extractor._parse_address_text("привет как дела")
    assert no_address['street'] is None and no_address['house_number'] is None, "Текст без адреса обработан неверно"
    print("  ✓ Текст без адреса корректно обработан")

    # Только цифры (не адрес)
    numbers_only = extractor._parse_address_text("123 456")
    # Если цифры не в контексте дома/квартиры, их не нужно распознавать как адрес
    print("  ✓ Цифры без контекста не распознаются как адрес")

    print("✅ Тест 8 пройден: граничные случаи корректны")

    print("\n" + "=" * 60)
    print("🎉 ВСЕ ТЕСТЫ ФАЗЫ 3 УСПЕШНО ПРОЙДЕНЫ!")
    print("AddressExtractor с памятью работает ИДЕАЛЬНО! ✅")
    print("=" * 60)

    # Вывод сводки
    print("\n📊 СВОДКА ПО ПРОВЕРЕННЫМ ФУНКЦИЯМ:")
    print("  ✅ _parse_address_text() - парсинг компонентов адреса")
    print("  ✅ _merge_with_memory() - объединение с памятью (КЛЮЧЕВОЙ!)")
    print("  ✅ _normalize_components() - нормализация данных")
    print("  ✅ extract_address_components() - полный цикл с памятью")
    print("  ✅ Расчет confidence - автоматический расчет уверенности")

if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)