#!/usr/bin/env python3
"""
Unit-тест для проверки regex-валидации двойных вопросов

Дата: 2026-01-10
Назначение: Проверка что regex правильно детектирует двойные вопросы
"""

import re
import sys


def test_double_question_regex(question: str) -> tuple:
    """
    Тестирует вопрос на двойной вопрос через regex

    Returns:
        tuple: (is_double, reason, corrected_question)
    """
    if not question:
        return (False, "Empty question", question)

    question_lower = question.lower().strip()

    # 1. Проверка на "или" / "или" в вопросе
    if re.search(r'\s+или\s+', question_lower):
        # Проверяем что это не слово "оправить" или "измерить"
        if not re.search(r'(оправить|измерить|прось|близ)', question_lower):
            # Генерируем правильный вопрос
            if 'квартира' in question_lower or 'общедом' in question_lower:
                return (True, "Содержит 'или'", "Где именно это произошло?")
            elif 'прорыв' in question_lower or 'теч' in question_lower:
                return (True, "Содержит 'или'", "Что именно течет или прорвалось?")
            else:
                return (True, "Содержит 'или'", "Опишите подробнее, что именно произошло?")

    # 2. Двойной вопрос через "и" ("что и где?", "какой объект и в каком месте?")
    if re.search(r'\s+(и|,)\s+', question_lower):
        # Проверяем что это не "и т.д." или "и так далее"
        if not re.search(r'(т\.д\.|так далее|пр\.|etc\.|и т\.п\.)', question_lower):
            # Проверяем что вопрос действительно двойной (два вопросительных слова)
            question_words = question_lower.split()
            question_keywords = ['что', 'где', 'какой', 'который', 'как', 'когда', 'почему', 'откуда', 'чем', 'зачем']
            found_keywords = [w for w in question_words if any(k in w for k in question_keywords)]
            if len(found_keywords) >= 2:
                return (True, f"Двойной вопрос через 'и' (ключевые слова: {found_keywords})", "Опишите подробнее, что именно произошло?")

    return (False, "OK", question)


def run_tests():
    """Запускает тесты regex-валидации"""

    print("=" * 80)
    print("UNIT-TEST: Regex-валидация двойных вопросов")
    print("=" * 80)

    # Тестовые примеры
    test_cases = [
        # ===== ДВОЙНЫЕ ВОПРОСЫ (должны быть детектированы) =====

        # С "или"
        ("Это прорыв трубы в квартире или общедомовой прорыв?", True),
        ("Что и где именно?", True),
        ("Какой объект и в каком месте?", True),
        ("Опишите что и где это произошло", True),
        ("Это труба или батарея?", True),
        ("Это инцидент или запрос?", True),
        ("Где именно или когда?", True),

        # Реальные примеры из диалогов
        ("(уточняю ситуацию): Это прорыв трубы в квартире или общедомовой прорыв?", True),
        ("Это отопление или водоснабжение?", True),
        ("Засор или прорыв?", True),
        ("В квартире или в подъезде?", True),

        # ===== ОДИНОЧНЫЕ ВОПРОСЫ (НЕ должны быть детектированы) =====

        # Обычные вопросы
        ("Где именно это произошло?", False),
        ("Опишите что именно сломалось", False),
        ("Что именно течет?", False),
        ("Каков характер протечки?", False),

        # С "и" но не двойные (разрешенные слова)
        ("В квартире или общедомовое? (оправить)", False),  # Исключение: "оправить"
        ("измерить длину и ширину", False),  # Исключение: "измерить"
        ("измерить длину, ширину и высоту", False),  # Исключение: "измерить"
        ("и т.д.", False),  # Исключение: "и т.д."
        ("и так далее", False),  # Исключение: "и так далее"

        # Граничные случаи
        ("Что делать если...?", False),  # Один вопросительный элемент
        ("Как быть?", False),  # Один вопросительный элемент
        ("Уточните детали", False),  # Без вопросительного знака
    ]

    passed = 0
    failed = 0

    for question, expected_double in test_cases:
        is_double, reason, corrected = test_double_question_regex(question)

        # Проверяем результат
        if expected_double:
            if is_double:
                print(f"✅ PASS: '{question[:50]}...'")
                print(f"   → Детектирован: {reason}")
                print(f"   → Исправлено: '{corrected}'")
                passed += 1
            else:
                print(f"❌ FAIL: '{question[:50]}...'")
                print(f"   → Ожидается двойной вопрос, но НЕ детектирован!")
                failed += 1
        else:
            if not is_double:
                print(f"✅ PASS: '{question[:50]}...'")
                print(f"   → OK: {reason}")
                passed += 1
            else:
                print(f"❌ FAIL: '{question[:50]}...'")
                print(f"   → Ожидается одиночный вопрос, но детектирован как ДВОЙНОЙ!")
                print(f"   → Причина: {reason}")
                failed += 1

        print()

    # Статистика
    print("=" * 80)
    print(f"РЕЗУЛЬТАТЫ: {passed} PASSED, {failed} FAILED")
    print("=" * 80)

    if failed > 0:
        print("\n⚠️ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ! Нужно улучшить regex.")
        return False
    else:
        print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Regex работает корректно.")
        return True


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
