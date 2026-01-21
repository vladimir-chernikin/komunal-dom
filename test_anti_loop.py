#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест защиты от зацикливания коммуникативных скриптов

Дата: 2026-01-21
Назначение: Проверить, что бот не зацикливается на fallback вопросах

Запуск:
    python test_anti_loop.py
"""

import asyncio
import sys
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/komunal-dom_ru')

from main_agent import MainAgent


async def test_anti_loop():
    """Тест защиты от зацикливания"""

    print("=" * 80)
    print("ТЕСТ: Защита от зацикливания коммуникативных скриптов")
    print("=" * 80)
    print()

    agent = MainAgent()
    session_id = f"test_anti_loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Абсурдные сообщения - бот не сможет определить услугу
    messages = [
        "привет",
        "абракадабра",
        "фырфырфыр",
        "бла бла бла",
        "ёклмн",
        "хз что",
        "еще раз",  # ← Здесь должно сработать защита
        "не знаю",
        "чтото",
        "ну"
    ]

    protection_activated = False
    protection_turn = None

    for i, msg in enumerate(messages, 1):
        print(f"\n{'─' * 80}")
        print(f"ХОД {i}")
        print(f"{'─' * 80}")
        print(f"Пользователь: {msg}")

        try:
            result = await agent.process_message(
                message_text=msg,
                session_id=session_id,
                channel='test_bot'
            )

            bot_message = result.get('message', '???')
            print(f"Бот: {bot_message[:150]}")

            # Проверяем, сработала ли защита
            if "оператор" in bot_message.lower() and "не смог определить" in bot_message.lower():
                protection_activated = True
                protection_turn = i
                print()
                print("✅ ЗАЩИТА ОТ ЗАЦИКЛИВАНИЯ СРАБОТАЛА!")
                print(f"   Ход активации: {i}")
                print()

                # Проверяем, что защита сработала на правильном ходу
                if i == 7:
                    print("✅ ВЕРНО: Защита сработала на 7-м ходу (как ожидалось)")
                elif i < 7:
                    print(f"⚠️  РАНО: Защита сработала на {i}-м ходу (ожидалось 7+)")
                else:
                    print(f"⚠️  ПОЗДНО: Защита сработала на {i}-м ходу (ожидалось 7)")

        except Exception as e:
            print(f"❌ ОШИБКА: {e}")

    print(f"\n{'=' * 80}")
    print("РЕЗУЛЬТАТЫ ТЕСТА")
    print(f"{'=' * 80}")
    print()

    if protection_activated:
        print(f"✅ ЗАЩИТА СРАБОТАЛА на ходу {protection_turn}")
        print()
        print("Ожидается: защита должна сработать на 7-м ходу или позже")

        if protection_turn == 7:
            print("✅ Идеально: защита сработала точно на 7-м ходу")
            return True
        elif protection_turn > 7:
            print(f"⚠️  Защита сработала поздно ({protection_turn} > 7)")
            print("   Это может указывать на проблему в логике dialog_turn")
            return False
        else:
            print(f"⚠️  Защита сработала рано ({protection_turn} < 7)")
            print("   Возможно, нужно увеличить порог срабатывания")
            return False
    else:
        print("❌ ЗАЩИТА НЕ СРАБОТАЛА")
        print()
        print("Возможные причины:")
        print("1. Защита не добавлена в код")
        print("2. Неправильно вычисляется dialog_turn")
        print("3. Бот успешно определил услугу (не fallback)")
        print()
        print("Рекомендация: соберите трассировку для анализа")
        print(f"Session ID: {session_id}")
        return False


async def test_db_scripts():
    """Проверка скриптов в БД"""

    print(f"\n{'=' * 80}")
    print("ПРОВЕРКА: Скрипты в БД")
    print(f"{'=' * 80}")
    print()

    import os
    import psycopg2
    from dotenv import load_dotenv

    load_dotenv()

    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=os.getenv('DB_PORT', 5432),
            database=os.getenv('DB_NAME', 'aspect_objects_db'),
            user=os.getenv('DB_USER', 'aspect_db'),
            password=os.getenv('DB_PASSWORD', 'DB_Aspect_2025')
        )

        cursor = conn.cursor()

        # Проверяем fallback скрипты
        cursor.execute("""
            SELECT script_name, min_dialog_turn, max_dialog_turn
            FROM message_handler_communicativescript
            WHERE script_type = 'fallback'
            ORDER BY min_dialog_turn, priority;
        """)

        scripts = cursor.fetchall()

        print("FALLBACK СКРИПТЫ:")
        print(f"{'Скрипт':<30} {'min_turn':<10} {'max_turn':<10}")
        print("─" * 50)

        for script_name, min_turn, max_turn in scripts:
            print(f"{script_name:<30} {min_turn:<10} {max_turn:<10}")

        print()

        # Проверяем наличие финального скрипта
        cursor.execute("""
            SELECT COUNT(*)
            FROM message_handler_communicativescript
            WHERE script_name = 'fallback_final_operator';
        """)

        count = cursor.fetchone()[0]

        if count > 0:
            print("✅ Финальный fallback скрипт присутствует в БД")
        else:
            print("❌ Финальный fallback скрипт ОТСУТСТВУЕТ в БД!")

        cursor.close()
        conn.close()

        return count > 0

    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False


async def main():
    """Главная функция"""

    # Тест 1: Проверка скриптов в БД
    db_ok = await test_db_scripts()

    print()

    # Тест 2: Проверка защиты от зацикливания
    protection_ok = await test_anti_loop()

    print()
    print("=" * 80)
    print("ИТОГОВЫЙ РЕЗУЛЬТАТ")
    print("=" * 80)
    print()

    if db_ok and protection_ok:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print()
        print("Защита от зацикливания работает корректно:")
        print("1. Скрипты в БД настроены правильно")
        print("2. Защита в коде срабатывает на 7-м ходу")
        return 0
    else:
        print("❌ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        print()
        if not db_ok:
            print("❌ Скрипты в БД настроены неправильно")
        if not protection_ok:
            print("❌ Защита от зацикливания не работает")
        print()
        print("Рекомендация:")
        print("1. Проверьте миграцию: message_handler/migrations/fix_communicative_scripts_loop.sql")
        print("2. Соберите трассировку для анализа")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
