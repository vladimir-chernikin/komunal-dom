#!/usr/bin/env python3
"""
Тест сценария "течет батарея"

ПРОВЕРЯЕТ:
1. Что бот НЕ задаёт лишний вопрос "Опишите подробнее..."
2. Что после "в зале" сразу создаётся заявка
3. Что стоимость уменьшилась (было 11.80 руб, ожидаем ~7-8 руб)
"""

import asyncio
import sys
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/komunal-dom_ru')

# Django setup
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from message_handler_service import MessageHandlerService

async def test_techet_batera():
    """Тест сценария 'течет батарея'"""

    print("\n" + "="*80)
    print("ТЕСТ СЦЕНАРИЯ: 'течет батарея'")
    print("="*80)

    # Инициализация
    handler = MessageHandlerService()
    session_id = f"test_techet_batera_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    user_id = "test_user_battery"

    print("\n--- Шаг 1: 'течет батарея' ---")
    result1 = await handler.handle_incoming_message(
        text="течет батарея",
        user_id=user_id,
        session_id=session_id,
        channel="test_bot"
    )

    message1 = result1.get('message', '')
    print(f"Бот: {message1}")
    print(f"Статус: {result1.get('status')}")
    print(f"Кандидатов: {len(result1.get('candidates', []))}")

    # Пауза перед следующим сообщением
    await asyncio.sleep(1)

    print("\n--- Шаг 2: 'в зале' ---")
    result2 = await handler.handle_incoming_message(
        text="в зале",
        user_id=user_id,
        session_id=session_id,
        channel="test_bot"
    )

    message2 = result2.get('message', '')
    print(f"Бот: {message2}")
    print(f"Статус: {result2.get('status')}")

    # Анализ результатов
    print("\n" + "="*80)
    print("АНАЛИЗ РЕЗУЛЬТАТОВ:")
    print("="*80)

    # Проверка 1: Первый вопрос
    if "комнат" in message1.lower() or "где" in message1.lower():
        print("✅ Шаг 1: Бот задал вопрос о локации")
    else:
        print("❌ Шаг 1: Бот НЕ задал вопрос о локации")

    # Проверка 2: Второй шаг - создание заявки
    if "заявк" in message2.lower():
        print("✅ Шаг 2: После 'в зале' создана заявка")
    else:
        print("❌ Шаг 2: После 'в зале' НЕ создана заявка")
        print(f"   Вместо этого бот сказал: '{message2}'")

    # Проверка 3: Лишний вопрос
    if "подробн" in message2.lower() or "как именно" in message2.lower():
        print("❌ Шаг 2: Бот задал ЛИШНИЙ вопрос 'Опишите подробнее...'")
    else:
        print("✅ Шаг 2: Бот НЕ задал лишний вопрос")

    # Генерация трассировки для анализа стоимости
    print("\n" + "="*80)
    print("ГЕНЕРАЦИЯ ТРАССИРОВКИ:")
    print("="*80)

    from trace_report_service import TraceReportService

    trace_report = await TraceReportService.generate_trace_report(
        session_id=session_id,
        output_format='markdown'
    )

    # Сохранение в файл
    from pathlib import Path
    output_path = Path(f'/tmp/_tras_diag_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md')
    output_path.write_text(trace_report, encoding='utf-8')
    os.chmod(output_path, 0o644)

    print(f"✅ Трассировка сохранена: {output_path}")
    print(f"   Для просмотра: cat {output_path}")

    # Проверка стоимости (парсинг из трассировки)
    total_cost = 0.0
    for line in trace_report.split('\n'):
        if '💰 Итого' in line or 'Итого стоимость' in line:
            # Извлекаем число из строки
            import re
            match = re.search(r'(\d+\.?\d*)\s*руб', line)
            if match:
                total_cost = float(match.group(1))

    print(f"\n💰 Общая стоимость: {total_cost:.2f} руб")

    if total_cost <= 9.0:
        print("✅ Стоимость в норме (≤9 руб)")
    elif total_cost <= 12.0:
        print("⚠️ Стоимость немного выше нормы (9-12 руб)")
    else:
        print(f"❌ Стоимость TOO HIGH ({total_cost:.2f} руб > 12 руб)")

    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(test_techet_batera())
