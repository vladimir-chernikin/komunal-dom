"""
TraceReportService - Сервис для генерации полных отчетов трассировки диалогов

Автоматически создает файлы _tras_diag(дата_время).md с полной трассировкой
по шаблону из CLAUDE.md.

Использование:
    from trace_report_service import TraceReportService
    from datetime import datetime

    service = TraceReportService()
    await service.generate_trace_report(session_id='telegram_123456')
    # Создаст файл: /tmp/_tras_diag_20251226_074500.md

Автор: Claude Sonnet
Дата: 2025-12-26
"""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class TraceReportService:
    """
    Сервис для генерации полных отчетов трассировки диалогов по шаблону CLAUDE.md.
    """

    def __init__(self):
        self.tmp_dir = Path('/tmp')

    async def generate_trace_report(
        self,
        session_id: str,
        messages: List[Dict] = None,
        output_path: str = None
    ) -> str:
        """
        Генерирует полный отчет трассировки диалога.

        Args:
            session_id: ID сессии для трассировки
            messages: Список сообщений (если None - загрузит из БД)
            output_path: Путь для сохранения файла (если None - авто-имя)

        Returns:
            str: Путь к созданному файлу
        """
        # Загружаем сообщения если не переданы
        if messages is None:
            messages = await self._load_messages_from_db(session_id)

        if not messages:
            logger.warning(f"Нет сообщений для сессии {session_id}")
            return None

        # Генерируем отчет
        report_content = self._generate_full_report(session_id, messages)

        # Определяем путь к файлу
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = self.tmp_dir / f'_tras_diag_{timestamp}.md'
        else:
            output_path = Path(output_path)

        # Сохраняем отчет
        output_path.write_text(report_content, encoding='utf-8')

        # Устанавливаем права на чтение для всех (фикс для веб-сервера www-data)
        import os
        os.chmod(output_path, 0o644)  # rw-r--r--
        logger.info(f"Создан отчет трассировки: {output_path} (права: 644)")

        return str(output_path)

    async def _load_messages_from_db(self, session_id: str) -> List[Dict]:
        """Загружает сообщения из базы данных напрямую через psycopg2."""
        try:
            from django.conf import settings
            import psycopg2
            from asgiref.sync import sync_to_async

            def load_sync():
                # Подключаемся напрямую к БД, минуя Django connection wrapper
                # Это избегает проблем с thread_sharing в async контексте
                conn = psycopg2.connect(
                    host=settings.DATABASES['default']['HOST'],
                    port=settings.DATABASES['default']['PORT'],
                    database=settings.DATABASES['default']['NAME'],
                    user=settings.DATABASES['default']['USER'],
                    password=settings.DATABASES['default']['PASSWORD']
                )

                try:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT
                                id,
                                text,
                                direction,
                                channel,
                                session_id,
                                created_at,
                                metadata
                            FROM message_handler_messagelog
                            WHERE session_id LIKE %s
                            ORDER BY created_at ASC
                        """, [f"{session_id}%"])

                        columns = [col[0] for col in cursor.description]
                        messages = []
                        for row in cursor.fetchall():
                            messages.append(dict(zip(columns, row)))

                        return messages
                finally:
                    conn.close()

            messages = await sync_to_async(load_sync)()
            logger.info(f"Загружено {len(messages)} сообщений для сессии {session_id}")
            return messages

        except Exception as e:
            logger.error(f"Ошибка загрузки сообщений: {e}")
            return []

    def _generate_full_report(self, session_id: str, messages: List[Dict]) -> str:
        """Генерирует полный отчет по шаблону CLAUDE.md."""

        # Базовая информация
        channel = messages[0].get('channel', 'unknown') if messages else 'unknown'
        first_msg_time = messages[0].get('created_at') if messages else None
        last_msg_time = messages[-1].get('created_at') if messages else None

        # Извлекаем txtPrb из metadata
        txtPrb_history = self._extract_txtPrb_history(messages)

        # Формируем отчет
        report = f"""================================================================================
ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА (по шаблону CLAUDE.md)
================================================================================
Session ID: {session_id}
Канал: {channel}
Всего сообщений: {len(messages)}
Период: {first_msg_time} - {last_msg_time}

================================================================================
ИСТОРИЯ txtPrb (накопление описания проблемы)
================================================================================
"""

        if txtPrb_history:
            for i, entry in enumerate(txtPrb_history, 1):
                msg_num = entry['message_num']
                txtPrb = entry['txtPrb']
                if txtPrb:
                    report += f"\n#{msg_num}: {txtPrb}\n"
                else:
                    report += f"\n#{msg_num}: (нет значимой информации)\n"
        else:
            report += "\n(нет данных txtPrb)\n"

        report += "\n"
        report += "=" * 80 + "\n"
        report += "ДЕТАЛЬНАЯ ТРАССИРОВКА ПО СООБЩЕНИЯМ\n"
        report += "=" * 80 + "\n\n"

        # Детальная трассировка каждого сообщения
        for i, msg in enumerate(messages, 1):
            report += self._format_message_details(i, msg, txtPrb_history)

        # Статистика
        report += "\n"
        report += "=" * 80 + "\n"
        report += "СТАТИСТИКА ДИАЛОГА\n"
        report += "=" * 80 + "\n"
        report += self._generate_statistics(messages)

        report += "\n"
        report += "=" * 80 + "\n"
        report += f"ДАТА ГЕНЕРАЦИИ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += "ШАБЛОН: CLAUDE.md DialogTraceService\n"
        report += "=" * 80 + "\n"

        return report

    def _extract_txtPrb_history(self, messages: List[Dict]) -> List[Dict]:
        """Извлекает историю txtPrb из metadata сообщений."""
        history = []
        for i, msg in enumerate(messages, 1):
            metadata = msg.get('metadata', {})
            if isinstance(metadata, dict):
                txtPrb = metadata.get('txtPrb', '')
                history.append({
                    'message_num': i,
                    'txtPrb': txtPrb
                })
        return history

    def _format_message_details(self, num: int, msg: Dict, txtPrb_history: List[Dict]) -> str:
        """Форматирует детали сообщения."""
        direction = msg.get('direction', 'unknown')
        text = msg.get('text', '')
        created_at = msg.get('created_at', '')
        channel = msg.get('channel', '')
        msg_id = msg.get('id', '')

        # Находим txtPrb для этого сообщения
        txtPrb = ""
        if num - 1 < len(txtPrb_history):
            txtPrb = txtPrb_history[num - 1].get('txtPrb', '')

        direction_label = "inbound (пользователь → бот)" if direction == 'inbound' else "outbound (бот → пользователь)"
        icon = "👤" if direction == 'inbound' else "🤖"

        details = f"""
{'=' * 80}
СООБЩЕНИЕ #{num}
{'-' * 80}
ID: {msg_id}
Направление: {direction_label}
Текст: "{text}"
Время: {created_at}
Канал: {channel}
"""

        # Добавляем txtPrb если есть
        if txtPrb:
            details += f"""
ИЗВЕСТНАЯ ИНФОРМАЦИЯ (txtPrb):
{txtPrb}
"""

        # Добавляем metadata
        metadata = msg.get('metadata', {})
        if metadata:
            details += f"""
METADATA:
{self._format_metadata(metadata)}
"""

        # Добавляем заключение о результате шага
        details += f"""
{'-' * 80}
ЗАКЛЮЧЕНИЕ ШАГА #{num}:
"""
        if direction == 'inbound':
            # Входящее сообщение от пользователя
            if txtPrb:
                details += f"✅ Пользователь предоставил информацию. Текущее понимание: {txtPrb}"
            else:
                details += "⚠️ Входящее сообщение не содержит значимой информации для определения проблемы"
        else:
            # Исходящее сообщение от бота
            service_detection = metadata.get('service_detection', {})
            status = service_detection.get('status', 'unknown')

            if status == 'SUCCESS':
                service_name = service_detection.get('service_name', 'неизвестно')
                details += f"✅ Услуга определена: {service_name}"
            elif status == 'AMBIGUOUS':
                candidates_count = len(service_detection.get('candidates', []))
                details += f"⚠️ Требуется уточнение. Найдено кандидатов: {candidates_count}"
            elif status == 'NOT_FOUND':
                details += "❌ Услуга не найдена. Требуется уточнение проблемы"
            else:
                details += f"🔍 Статус обработки: {status}"

        details += "\n"

        return details

    def _format_metadata(self, metadata, indent: str = "  ") -> str:
        """Форматирует metadata для вывода."""
        import json

        # Если metadata - строка, пробуем распарсить JSON
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                return f"{indent}{metadata}"

        if not isinstance(metadata, dict):
            return f"{indent}{metadata}"

        lines = []
        for key, value in metadata.items():
            if key == 'txtPrb':
                continue  # Уже вывели отдельно
            if isinstance(value, dict):
                lines.append(f"{indent}{key}:")
                lines.append(self._format_metadata(value, indent + "  "))
            elif isinstance(value, list):
                lines.append(f"{indent}{key}: {value}")
            else:
                value_str = str(value)[:100]  # Ограничиваем длину
                lines.append(f"{indent}{key}: {value_str}")
        return "\n".join(lines)

    def _generate_statistics(self, messages: List[Dict]) -> str:
        """Генерирует статистику диалога."""
        inbound_count = sum(1 for m in messages if m.get('direction') == 'inbound')
        outbound_count = sum(1 for m in messages if m.get('direction') == 'outbound')

        # Извлекаем txtPrb из последнего сообщения
        final_txtPrb = ""
        for msg in reversed(messages):
            metadata = msg.get('metadata', {})
            if isinstance(metadata, dict) and 'txtPrb' in metadata:
                final_txtPrb = metadata['txtPrb']
                break

        stats = f"""
Всего сообщений: {len(messages)}
  - Входящих (пользователь): {inbound_count}
  - Исходящих (бот): {outbound_count}

Финальное описание проблемы (txtPrb):
{final_txtPrb if final_txtPrb else '(не накоплено)'}

Канал связи: {messages[0].get('channel', 'unknown') if messages else 'unknown'}
"""
        return stats


# Удобная функция для быстрого вызова
async def generate_dialog_trace(session_id: str, output_path: str = None) -> str:
    """
    Быстрая генерация трассировки диалога.

    Пример:
        from trace_report_service import generate_dialog_trace
        await generate_dialog_trace('telegram_123456')
        # Создаст файл /tmp/_tras_diag_20251226_074500.md
    """
    service = TraceReportService()
    return await service.generate_trace_report(session_id, output_path=output_path)


# Если вызывается напрямую
if __name__ == '__main__':
    import sys
    import django

    # Инициализируем Django
    sys.path.insert(0, '/var/www/komunal-dom_ru')
    django.setup()

    async def main():
        session_id = sys.argv[1] if len(sys.argv) > 1 else 'telegram_1049252307'
        service = TraceReportService()
        path = await service.generate_trace_report(session_id)
        if path:
            print(f"Отчет создан: {path}")
        else:
            print("Не удалось создать отчет")

    asyncio.run(main())
