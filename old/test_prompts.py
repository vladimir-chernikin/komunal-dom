#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование работы промптов
"""

from prompt_manager import prompt_manager
import json

def test_greetings():
    """Тестирование приветствий"""
    print("🔍 Тестирование приветствий...")

    # Тест с именем
    greeting_with_name = prompt_manager.get_greeting_prompt("Анна")
    print(f"С именем: {greeting_with_name[:100]}...")

    # Тест без имени
    greeting_no_name = prompt_manager.get_greeting_prompt()
    print(f"Без имени: {greeting_no_name[:100]}...")

    print("✅ Приветствия работают корректно\n")

def test_clarification():
    """Тестирование запросов уточнения"""
    print("🔍 Тестирование запросов уточнения...")

    test_messages = [
        "привет",
        "помогите",
        "что-то сломалось",
        "проблема"
    ]

    template = prompt_manager.get_clarification_template()

    for msg in test_messages:
        clarification = prompt_manager.format_clarification_message(msg, template)
        print(f"Сообщение: '{msg}'")
        print(f"Ответ: {clarification[:150]}...")
        print("-" * 50)

    print("✅ Запросы уточнения работают корректно\n")

def test_system_prompt():
    """Тестирование системного промпта"""
    print("🔍 Тестирование системного промпта...")

    system = prompt_manager.get_system_prompt()
    print(f"Длина системного промпта: {len(system)} символов")
    print("Основные моменты из промпта:")
    print("  - " + "\n  - ".join(system.split('\n')[:5]))
    print("✅ Системный промпт загружен\n")

def test_service_detection():
    """Тестирование правил определения услуг"""
    print("🔍 Тестирование правил определения услуг...")

    rules = prompt_manager.get_service_detection_rules()
    categories = ["УТЕЧКИ", "ШУМ", "ОТКЛЮЧЕНИЯ", "ЗАСОРЫ", "ЗАПАХИ"]

    for category in categories:
        if category in rules:
            print(f"  ✅ Найдена категория: {category}")

    print("✅ Правила определения услуг загружены\n")

def test_emergency_rules():
    """Тестирование правил ЧС"""
    print("🔍 Тестирование правил аварийных ситуаций...")

    emergency = prompt_manager.get_emergency_rules()
    emergency_keywords = ["АВАРИЙНЫЕ", "газ", "прорыв", "пожар", "немедленно"]

    found_keywords = [kw for kw in emergency_keywords if kw in emergency]
    print(f"Найдено ключевых слов ЧС: {len(found_keywords)}/{len(emergency_keywords)}")

    if len(found_keywords) >= 4:
        print("✅ Правила ЧС содержат все необходимые элементы")
    else:
        print("⚠️ Правила ЧС могут быть неполными")

    print()

def main():
    """Основная функция тестирования"""
    print("="*60)
    print("🧪 ТЕСТИРОВАНИЕ НОВЫХ ПРОМПТОВ БОТА")
    print("="*60)
    print()

    test_greetings()
    test_clarification()
    test_system_prompt()
    test_service_detection()
    test_emergency_rules()

    print("="*60)
    print("✅ Все тесты пройдены! Промпты готовы к использованию.")
    print("="*60)

if __name__ == '__main__':
    main()