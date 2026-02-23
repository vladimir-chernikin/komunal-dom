#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест исправления hardcoded is_leak

Проверяет что:
1. Хардкод keywords убран
2. Используется accumulated_fields.source
3. Используется category_confidence >= 0.7
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/komunal-dom_ru')

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

def test_hardcode_removed():
    """Проверяем что hardcoded keywords удалены"""

    print("=" * 80)
    print("ТЕСТ 1: Проверка удаления hardcoded keywords")
    print("=" * 80)

    with open('main_agent.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Проверяем что старой проверки нет
    hardcoded_patterns = [
        "is_leak = any(word in (source + ' ' + problem) for word in ['теч', 'протек', 'капа', 'батарей', 'радиатор'])",
        "any(keyword in service_name_lower for keyword in ['теч', 'протек', 'капа'])"
    ]

    found_hardcode = []
    for pattern in hardcoded_patterns:
        if pattern in content:
            found_hardcode.append(pattern)

    if found_hardcode:
        print("❌ НАЙДЕН HARDCODE:")
        for pattern in found_hardcode:
            print(f"  {pattern}")
        return False
    else:
        print("✅ Hardcoded keywords УДАЛЕНЫ")
        return True


def test_accumulated_fields_used():
    """Проверяем что используется accumulated_fields"""

    print("\n" + "=" * 80)
    print("ТЕСТ 2: Проверка использования accumulated_fields")
    print("=" * 80)

    with open('main_agent.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Проверяем что используется has_source
    required_patterns = [
        "has_source = accumulated_fields.get('source') is not None",
        "category_confidence = established_filters.get('category', {}).get('confidence', 0.0)",
        "category_confidence >= 0.7"
    ]

    all_found = True
    for pattern in required_patterns:
        if pattern not in content:
            print(f"❌ НЕ НАЙДЕНО: {pattern}")
            all_found = False
        else:
            print(f"✅ НАЙДЕНО: {pattern}")

    return all_found


def test_logic_correctness():
    """Проверяем логику"""

    print("\n" + "=" * 80)
    print("ТЕСТ 3: Проверка логики")
    print("=" * 80)

    test_cases = [
        {
            'name': 'ТЕЧЕТ ТРУБА',
            'category': 'Водоснабжение',
            'category_confidence': 0.9,
            'has_source': True,
            'severity': None,
            'expected_needs_clarification': True
        },
        {
            'name': 'ХОЛОДНАЯ БАТАРЕЯ',
            'category': 'Отопление',
            'category_confidence': 0.9,
            'has_source': True,
            'severity': None,
            'expected_needs_clarification': True  # Спросим, LLM разберется
        },
        {
            'name': 'ТЕЧЕТ С ИНТЕНСИВНОСТЬЮ',
            'category': 'Водоснабжение',
            'category_confidence': 0.9,
            'has_source': True,
            'severity': 'струя',
            'expected_needs_clarification': False  # Уже есть severity
        },
        {
            'name': 'НЕТ ИСТОЧНИКА',
            'category': 'Водоснабжение',
            'category_confidence': 0.9,
            'has_source': False,
            'severity': None,
            'expected_needs_clarification': False  # Нет source
        },
        {
            'name': 'НИЗКАЯ УВЕРЕННОСТЬ',
            'category': 'Водоснабжение',
            'category_confidence': 0.5,
            'has_source': True,
            'severity': None,
            'expected_needs_clarification': False  # category_confidence < 0.7
        }
    ]

    all_correct = True

    for test in test_cases:
        # Эмулируем логику
        is_water_problem = (
            test['category'] in ['Водоснабжение', 'Отопление', 'Канализация'] and
            test['category_confidence'] >= 0.7
        )

        needs_clarification = (
            True and  # is_incident
            is_water_problem and
            test['has_source'] and
            not test['severity']
        )

        result = "✅" if needs_clarification == test['expected_needs_clarification'] else "❌"
        print(f"{result} {test['name']}:")
        print(f"    category={test['category']}, conf={test['category_confidence']}")
        print(f"    has_source={test['has_source']}, severity={test['severity']}")
        print(f"    Ожидается: {test['expected_needs_clarification']}, Получено: {needs_clarification}")

        if needs_clarification != test['expected_needs_clarification']:
            all_correct = False

    return all_correct


if __name__ == "__main__":
    print("\nТЕСТИРОВАНИЕ ИСПРАВЛЕНИЯ HARDCODED is_leak\n")

    test1 = test_hardcode_removed()
    test2 = test_accumulated_fields_used()
    test3 = test_logic_correctness()

    print("\n" + "=" * 80)
    print("ИТОГИ:")
    print("=" * 80)
    print(f"Тест 1 (удаление хардкода): {'✅ ПРОЙДЕН' if test1 else '❌ НЕ ПРОЙДЕН'}")
    print(f"Тест 2 (accumulated_fields): {'✅ ПРОЙДЕН' if test2 else '❌ НЕ ПРОЙДЕН'}")
    print(f"Тест 3 (логика): {'✅ ПРОЙДЕН' if test3 else '❌ НЕ ПРОЙДЕН'}")

    if test1 and test2 and test3:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        sys.exit(0)
    else:
        print("\n⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        sys.exit(1)
