#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для ФАЗЫ 2: AntiSpamFilter с 4 уровнями проверки
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
    print("🧪 НАЧИНАЕМ ТЕСТЫ ФАЗЫ 2: AntiSpamFilter")
    print("=" * 60)

    from service_detection_modules import AntiSpamFilter

    spam_filter = AntiSpamFilter()

    # Тест 1: Обнаружение ругательства
    print("\n📝 Тест 1: Обнаружение ругательства")
    result = spam_filter.check_message("Хуй знает что здесь")
    assert result['category'] == 'PROFANITY', f"Ожидалась категория PROFANITY, получена {result['category']}"
    assert result['is_spam'] == True, f"Ожидался is_spam=True, получен {result['is_spam']}"
    assert 'details' in result, "Отсутствует детализация в ответе"
    assert result['details'].get('found') == True, "В детализации не найден флаг found=True"
    print("✅ Тест 1 пройден: обнаружение ругательства")
    print(f"   Слово: {result['details'].get('word', 'N/A')}")
    print(f"   Строгость: {result.get('confidence', 'N/A')}")
    print(f"   Количество: {result['details'].get('count', 'N/A')}")

    # Тест 2: Обнаружение неконструктивности
    print("\n😠 Тест 2: Обнаружение неконструктивности")
    result = spam_filter.check_message("Это полный отстой, не хочу ждать")
    assert result['category'] == 'NON_CONSTRUCTIVE', f"Ожидалась категория NON_CONSTRUCTIVE, получена {result['category']}"
    assert result['is_spam'] == True, f"Ожидался is_spam=True, получен {result['is_spam']}"
    assert result['action'] == 'WARN_AND_RETRY', f"Ожидалось действие WARN_AND_RETRY, получено {result['action']}"
    assert 'details' in result, "Отсутствует детализация в ответе"
    print("✅ Тест 2 пройден: обнаружение неконструктивности")
    print(f"   Действие: {result['action']}")
    print(f"   Паттерн: {result['details'].get('pattern', 'N/A')}")

    # Тест 3: Обнаружение расплывчатости
    print("\n🤔 Тест 3: Обнаружение расплывчатости")
    result = spam_filter.check_message("помогите")
    assert result['category'] == 'VAGUE', f"Ожидалась категория VAGUE, получена {result['category']}"
    assert result['is_spam'] == False, f"Ожидался is_spam=False (не спам), получен {result['is_spam']}"
    assert result['action'] == 'ASK_FOR_CLARIFICATION', f"Ожидалось действие ASK_FOR_CLARIFICATION, получено {result['action']}"
    print("✅ Тест 3 пройден: обнаружение расплывчатости")
    print(f"   Действие: {result['action']}")

    # Тест 4: OK сообщение
    print("\n✅ Тест 4: Нормальное сообщение")
    result = spam_filter.check_message("Протекает кран на кухне")
    assert result['category'] == 'OK', f"Ожидалась категория OK, получена {result['category']}"
    assert result['is_spam'] == False, f"Ожидался is_spam=False, получен {result['is_spam']}"
    assert result['action'] == 'PROCESS', f"Ожидалось действие PROCESS, получено {result['action']}"
    assert result['confidence'] == 1.0, f"Ожидалась уверенность 1.0, получена {result['confidence']}"
    print("✅ Тест 4 пройден: нормальное сообщение пропущено")
    print(f"   Уверенность: {result['confidence']}")

    # Тест 5: Базовый спам
    print("\n🚫 Тест 5: Базовый спам")
    result = spam_filter.check_message("http://example.com куплю недорого")
    assert result['category'] == 'SPAM', f"Ожидалась категория SPAM, получена {result['category']}"
    assert result['is_spam'] == True, f"Ожидался is_spam=True, получен {result['is_spam']}"
    assert result['action'] == 'REJECT', f"Ожидалось действие REJECT, получено {result['action']}"
    print("✅ Тест 5 пройден: обнаружение базового спама")
    print(f"   Действие: {result['action']}")

    # Тест 6: Несколько ругательств
    print("\n🤬 Тест 6: Несколько ругательств")
    result = spam_filter.check_message("Дебилы и козлы, пиздец какое поведение")
    assert result['category'] == 'PROFANITY', f"Ожидалась категория PROFANITY, получена {result['category']}"
    assert result['confidence'] > 0.7, f"Ожидалась высокая строгость при нескольких ругательствах, получена {result['confidence']}"
    print("✅ Тест 6 пройден: несколько ругательств")
    print(f"   Строгость: {result['confidence']:.2f}")

    # Тест 7: Граничное сообщение (не расплывчатое)
    print("\n🎯 Тест 7: Граничное сообщение")
    result = spam_filter.check_message("Проблема с краном")
    assert result['category'] == 'OK', f"Ожидалась категория OK, получена {result['category']}"
    print("✅ Тест 7 пройден: граничное сообщение распознано корректно")

    # Тест 8: Длинное сообщение с Caps Lock
    print("\n📢 Тест 8: Капслок")
    result = spam_filter.check_message("СРОЧНО ПОМОГИТЕ У МЕНЯ ПРОТЕКАЕТ КРАН")
    assert result['category'] == 'SPAM', f"Ожидалась категория SPAM из-за капслока, получена {result['category']}"
    print("✅ Тест 8 пройден: капслок обнаружен")

    print("\n" + "=" * 60)
    print("🎉 ВСЕ ТЕСТЫ ФАЗЫ 2 УСПЕШНО ПРОЙДЕНЫ!")
    print("AntiSpamFilter с 4 уровнями работает ИДЕАЛЬНО! ✅")
    print("=" * 60)

    # Вывод сводки
    print("\n📊 СВОДКА ПО КАТЕГОРИЯМ:")
    print("  ✅ OK - нормальные сообщения")
    print("  🚫 SPAM - явный спам (REJECT)")
    print("  🤬 PROFANITY - ругательства (WARN_AND_RETRY)")
    print("  😠 NON_CONSTRUCTIVE - неконструктив (WARN_AND_RETRY)")
    print("  🤔 VAGUE - расплывчатые (ASK_FOR_CLARIFICATION)")

    print("\n🔄 СТРУКТУРА ОТВЕТА:")
    print("  - is_spam: bool")
    print("  - reason: str")
    print("  - confidence: float")
    print("  - category: str")
    print("  - action: str")

if __name__ == "__main__":
    run_tests()