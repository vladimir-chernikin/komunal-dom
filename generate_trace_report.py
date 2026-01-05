#!/usr/bin/env python
"""
Генератор отчетов трассировки v3.0

Запуск:
    python generate_trace_report.py <session_id>

Пример:
    python generate_trace_report.py telegram_1049252307_20260105_143022
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from trace_report_v3 import TraceReportServiceV3


async def main():
    """Главная функция генерации отчета."""

    # Получаем session_id из аргументов командной строки
    if len(sys.argv) < 2:
        print("Использование: python generate_trace_report.py <session_id>")
        print("Пример: python generate_trace_report.py telegram_1049252307_20260105_143022")
        sys.exit(1)

    session_id = sys.argv[1]

    print(f"Генерация отчета для session_id: {session_id}")
    print("-" * 60)

    # Создаем сервис
    service = TraceReportServiceV3()

    # Генерируем отчет
    try:
        report = await service.generate_trace_report(session_id)

        # Проверяем на ошибку
        if report.startswith("# ОШИБКА:"):
            print(f"\n❌ {report}")
            sys.exit(1)

        # Сохраняем в файл
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"_tras_diag_v3_{timestamp}.md"
        output_path = Path('/tmp') / filename

        output_path.write_text(report, encoding='utf-8')

        # Устанавливаем права 644 для чтения веб-сервером
        os.chmod(output_path, 0o644)

        print(f"\n✅ Отчет успешно создан!")
        print(f"📁 Файл: {output_path}")
        print(f"📊 Размер: {output_path.stat().st_size} байт")
        print(f"\nПросмотр: cat {output_path}")

    except Exception as e:
        print(f"\n❌ Ошибка генерации отчета: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
