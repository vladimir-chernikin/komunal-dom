"""
TraceReportService - Улучшенный сервис для генерации отчетов трассировки диалогов

ИСПРАВЛЕНО (2025-12-28):
- txtPrb показывается на КАЖДОМ шаге
- Подробная расшифровка METADATA
- Candidates с разрезом по микросервисам
- Отдельный блок по фильтрам
- Правильное определение значимой информации
- Убраны все эмодзи (запрет проекта)

Использование:
    from trace_report_service import TraceReportService
    service = TraceReportService()
    await service.generate_trace_report(session_id='telegram_123456')
"""

import logging
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import os
import pytz

logger = logging.getLogger(__name__)

# ИСПРАВЛЕНО (2026-01-19): Добавлена конвертация timezone для отображения времени
# Настраиваем Django ДО импорта timezone
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from django.utils import timezone


class TraceReportService:
    """Улучшенный сервис для генерации отчетов трассировки диалогов."""

    # ИСПРАВЛЕНО (2025-12-29): Перевод статусов на русский
    STATUS_TRANSLATIONS = {
        'SUCCESS': 'Услуга определена',
        'AMBIGUOUS': 'Требуется уточнение',
        'ERROR': 'Ошибка обработки',
        'NOT_FOUND': 'Услуга не найдена',
        'unknown': 'Неизвестно'
    }

    def _translate_status(self, status: str) -> str:
        """Переводит статус на русский язык."""
        return self.STATUS_TRANSLATIONS.get(status, status)

    # ИСПРАВЛЕНО (2026-01-19): Метод для получения timezone пользователя из session_id
    def _get_user_timezone_from_session(self, session_id: str, messages: List[Dict] = None) -> str:
        """
        Получает часовой пояс пользователя по session_id.

        Args:
            session_id: ID сессии (например, 'web_1_...' или 'telegram_12345_...')
            messages: Список сообщений (опционально, для оптимизации)

        Returns:
            str: Часовой пояс (например, 'Europe/Moscow')
        """
        # ИСПРАВЛЕНО (2026-01-19): Импортируем sync_to_async для работы с Django ORM в async контексте
        from asgiref.sync import sync_to_async

        async def get_tz_async():
            try:
                # ИСПРАВЛЕНО (2026-01-19): Используем messages для получения django_user_id
                if messages and len(messages) > 0:
                    django_user_id = messages[0].get('django_user_id')
                    if django_user_id:
                        from portal.models import UserProfile
                        profile = await sync_to_async(UserProfile.objects.filter)(user__id=django_user_id).afirst()
                        if profile and profile.timezone:
                            return profile.timezone

                # Fallback на парсинг session_id
                if session_id.startswith('web_'):
                    parts = session_id.split('_')
                    if len(parts) >= 2:
                        try:
                            django_user_id = int(parts[1])
                            from portal.models import UserProfile
                            profile = await sync_to_async(UserProfile.objects.filter)(user__id=django_user_id).afirst()
                            if profile and profile.timezone:
                                return profile.timezone
                        except:
                            pass

            except Exception as e:
                logger.warning(f"Не удалось получить timezone пользователя: {e}")

            # Fallback РЅР° Moscow Time
            return 'Europe/Moscow'

        # Запускаем async функцию и получаем результат
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если цикл уже запущен, создаем задачу
                future = asyncio.ensure_future(get_tz_async())
                return asyncio.run_coroutine_threadsafe(future, loop).result(timeout=5)
            else:
                return asyncio.run(get_tz_async())
        except:
            return 'Europe/Moscow'

    # ИСПРАВЛЕНО (2026-01-19): Синхронная версия для получения timezone
    def _get_user_timezone_sync(self, session_id: str, messages: List[Dict] = None) -> str:
        """
        Синхронно получает часовой пояс пользователя по session_id.

        Args:
            session_id: ID сессии
            messages: Список сообщений (опционально)

        Returns:
            str: Часовой пояс (например, 'Europe/Moscow')
        """
        try:
            # ИСПРАВЛЕНО (2026-01-19): Используем messages для получения django_user_id
            if messages and len(messages) > 0:
                django_user_id = messages[0].get('django_user_id')
                if django_user_id:
                    from portal.models import UserProfile
                    profile = UserProfile.objects.filter(user__id=django_user_id).first()
                    if profile and profile.timezone:
                        return profile.timezone

            # Fallback на парсинг session_id
            if session_id.startswith('web_'):
                parts = session_id.split('_')
                if len(parts) >= 2:
                    try:
                        django_user_id = int(parts[1])
                        from portal.models import UserProfile
                        profile = UserProfile.objects.filter(user__id=django_user_id).first()
                        if profile and profile.timezone:
                            return profile.timezone
                    except:
                        pass

        except Exception as e:
            logger.warning(f"Не удалось получить timezone пользователя: {e}")

        # Fallback РЅР° Moscow Time
        return 'Europe/Moscow'

    # ИСПРАВЛЕНО (2026-01-19): Метод для конвертации UTC в часовой пояс пользователя
    def _format_datetime(self, dt: Any, user_timezone: str = None) -> str:
        """
        Конвертирует datetime из UTC в часовой пояс пользователя.

        Args:
            dt: datetime объект (может быть строкой или datetime)
            user_timezone: Часовой пояс пользователя (опционально)

        Returns:
            str: Отформатированная строка в часовом поясе пользователя
        """
        if dt is None:
            return '(нет времени)'

        # Если строка - парсим в datetime
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('+00:00', ''))
            except:
                return str(dt)

        try:
            # Если timezone не передан, используем серверный
            if user_timezone is None:
                local_dt = timezone.localtime(dt)
            else:
                # Конвертируем в timezone пользователя
                user_tz = pytz.timezone(user_timezone)
                if dt.tzinfo is None:
                    utc_dt = pytz.utc.localize(dt)
                else:
                    utc_dt = dt
                local_dt = utc_dt.astimezone(user_tz)

            return local_dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return str(dt)

    def __init__(self):
        self.tmp_dir = Path('/tmp')

    async def generate_trace_report(
        self,
        session_id: str,
        messages: List[Dict] = None,
        output_path: str = None,
        user_timezone: str = None
    ) -> str:
        """
        Генерирует улучшенный отчет трассировки диалога.

        ИСПРАВЛЕНО (2026-01-19): Добавлен параметр user_timezone для указания часового пояса.

        Args:
            session_id: ID сессии
            messages: Список сообщений (опционально)
            output_path: Путь для сохранения отчета (опционально)
            user_timezone: Часовой пояс пользователя (опционально, если None - определится автоматически)
        """

        # Загружаем сообщения если не переданы
        if messages is None:
            messages = await self._load_messages_from_db(session_id)

        if not messages:
            logger.warning(f"Нет сообщений для сессии {session_id}")
            return None

        # ИСПРАВЛЕНО (2026-01-06): Загружаем LLM запросы из таблицы llm_request_log
        llm_logs_map = await self._load_llm_logs_for_session(session_id, messages)
        fias_logs_map = await self._load_fias_logs_for_session(session_id)

        # ИСПРАВЛЕНО (2026-01-19): Определяем timezone пользователя
        if user_timezone is None:
            # Пробуем определить автоматически из session_id
            user_timezone = self._get_user_timezone_sync(session_id, messages)

        # Генерируем отчет
        report_content = self._generate_full_report(session_id, messages, llm_logs_map, user_timezone, fias_logs_map)

        # Определяем путь к файлу
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = self.tmp_dir / f'_tras_diag_{timestamp}.md'
        else:
            output_path = Path(output_path)

        # Сохраняем отчет
        output_path.write_text(report_content, encoding='utf-8')

        # Устанавливаем права на чтение для всех
        import os
        os.chmod(output_path, 0o644)
        logger.info(f"Создан отчет трассировки v2: {output_path}")

        return str(output_path)

    async def _load_messages_from_db(self, session_id: str) -> List[Dict]:
        """Загружает сообщения из БД."""
        try:
            from django.conf import settings
            import psycopg2

            def load_sync():
                conn = psycopg2.connect(
                    host=settings.DATABASES['default']['HOST'],
                    port=settings.DATABASES['default']['PORT'],
                    database=settings.DATABASES['default']['NAME'],
                    user=settings.DATABASES['default']['USER'],
                    password=settings.DATABASES['default']['PASSWORD']
                )
                try:
                    with conn.cursor() as cursor:
                        # ИСПРАВЛЕНО (2026-01-06): Используем dialog_logs вместо message_handler_messagelog
                        # ИСПРАВЛЕНО (2026-01-19): Добавлен django_user_id для определения timezone
                        # Алиасы для совместимости с существующим кодом
                        cursor.execute("""
                            SELECT
                                id,
                                message_id,
                                message_content as text,
                                direction,
                                channel,
                                session_id,
                                timestamp as created_at,
                                metadata,
                                django_user_id
                            FROM dialog_logs
                            WHERE session_id = %s
                            ORDER BY timestamp ASC
                        """, (session_id,))

                        columns = ['id', 'message_id', 'text', 'direction', 'channel', 'session_id', 'created_at', 'metadata', 'django_user_id']
                        messages = []
                        for row in cursor.fetchall():
                            msg = dict(zip(columns, row))
                            # Парсим metadata если строка
                            if msg['metadata'] is not None:
                                # Если это строка JSON - парсим
                                if isinstance(msg['metadata'], str):
                                    try:
                                        msg['metadata'] = json.loads(msg['metadata'])
                                    except:
                                        msg['metadata'] = {}
                                # Если это уже dict - оставляем как есть
                                elif not isinstance(msg['metadata'], dict):
                                    msg['metadata'] = {}
                            else:
                                msg['metadata'] = {}
                            messages.append(msg)
                        return messages
                finally:
                    conn.close()
                return messages

            return await asyncio.to_thread(load_sync)

        except Exception as e:
            logger.error(f"Ошибка загрузки сообщений: {e}")
            return []

    async def _load_llm_logs_for_session(self, session_id: str, messages: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Загружает LLM запросы для каждого сообщения из llm_request_log

        ИСПРАВЛЕНО (2026-01-06):
        - Берет промпты из таблицы llm_request_log вместо metadata
        - Связывает ПО session_id - надежное связывание вместо временного окна

        Args:
            session_id: ID сессии
            messages: Список сообщений из dialog_logs

        Returns:
            Dict: {message_id: [llm_requests]}
        """
        try:
            from django.conf import settings
            import psycopg2

            db_settings = settings.DATABASES['default']

            def load_llm_sync():
                conn = psycopg2.connect(
                    host=db_settings['HOST'],
                    database=db_settings['NAME'],
                    user=db_settings['USER'],
                    password=db_settings['PASSWORD'],
                    port=db_settings.get('PORT', 5432)
                )

                try:
                    with conn.cursor() as cursor:
                        # ИСПРАВЛЕНО (2026-01-06): Загружаем по session_id и связываем с message_id
                        # ИСПРАВЛЕНО (2026-03-13): Добавлено поле service_name
                        cursor.execute("""
                            SELECT
                                id,
                                provider,
                                model,
                                prompt_text,
                                response_text,
                                prompt_tokens,
                                completion_tokens,
                                total_tokens,
                                cost_rub,
                                created_at,
                                status,
                                error_message,
                                message_id,
                                caller_service,
                                prompt_slug,
                                prompt_source
                            FROM llm_request_log
                            WHERE session_id = %s
                            ORDER BY created_at ASC
                        """, (session_id,))

                        columns = ['id', 'provider', 'model', 'prompt_text', 'response_text',
                                   'prompt_tokens', 'completion_tokens', 'total_tokens', 'cost_rub',
                                   'created_at', 'status', 'error_message', 'message_id', 'caller_service',
                                   'prompt_slug', 'prompt_source']

                        all_llm_logs = []
                        for row in cursor.fetchall():
                            llm_log = dict(zip(columns, row))
                            all_llm_logs.append(llm_log)

                        # Связываем LLM запросы с сообщениями по message_id
                        # ИСПРАВЛЕНО (2026-01-06): Надежное связывание по message_id вместо временного окна
                        message_llm_map = {}

                        # Группируем LLM запросы по message_id
                        from collections import defaultdict
                        llm_by_message_id = defaultdict(list)
                        for llm in all_llm_logs:
                            if llm.get('message_id'):
                                llm_by_message_id[llm['message_id']].append(llm)

                        # Создаем map: message_id -> список LLM запросов
                        for msg in messages:
                            msg_id = msg['id']
                            if msg_id in llm_by_message_id:
                                message_llm_map[msg_id] = llm_by_message_id[msg_id]

                        logger.info(f"Загружено {len(all_llm_logs)} LLM запросов по session_id={session_id}, связано с {len(message_llm_map)} сообщений")
                        return message_llm_map

                finally:
                    conn.close()

            return await asyncio.to_thread(load_llm_sync)

        except Exception as e:
            logger.error(f"Ошибка загрузки LLM логов: {e}")
            return {}

    async def _load_fias_logs_for_session(self, session_id: str) -> Dict[int, List[Dict]]:
        """Загружает ФИАС-вызовы по session_id и связывает их с входящими сообщениями."""
        try:
            from django.conf import settings
            import psycopg2
            from decimal import Decimal
            from collections import defaultdict

            db_settings = settings.DATABASES['default']

            def json_safe(value):
                if isinstance(value, Decimal):
                    return float(value)
                if isinstance(value, dict):
                    return {key: json_safe(item) for key, item in value.items()}
                if isinstance(value, (list, tuple)):
                    return [json_safe(item) for item in value]
                if hasattr(value, 'isoformat'):
                    return value.isoformat()
                return value

            def load_fias_sync():
                conn = psycopg2.connect(
                    host=db_settings['HOST'],
                    database=db_settings['NAME'],
                    user=db_settings['USER'],
                    password=db_settings['PASSWORD'],
                    port=db_settings.get('PORT', 5432)
                )
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT
                                id,
                                endpoint,
                                method,
                                http_status,
                                duration_ms,
                                error_message,
                                fias_house_guid::text,
                                fias_street_guid::text,
                                building_id,
                                request_payload,
                                response_payload,
                                created_at,
                                message_log_id,
                                state_stage
                            FROM fias_request_log
                            WHERE session_id = %s
                            ORDER BY created_at ASC, id ASC
                        """, (session_id,))
                        rows = cursor.fetchall()
                finally:
                    conn.close()

                calls_by_message = defaultdict(list)
                for row in rows:
                    message_log_id = row[12]
                    if not message_log_id:
                        continue
                    calls_by_message[message_log_id].append({
                        'id': row[0],
                        'endpoint': row[1],
                        'method': row[2],
                        'http_status': row[3],
                        'duration_ms': json_safe(row[4]),
                        'error_message': row[5],
                        'fias_house_guid': row[6],
                        'fias_street_guid': row[7],
                        'building_id': row[8],
                        'request_payload': json_safe(row[9]),
                        'response_payload': json_safe(row[10]),
                        'created_at': row[11].isoformat() if row[11] else None,
                        'message_log_id': message_log_id,
                        'state_stage': row[13],
                    })
                return dict(calls_by_message)

            return await asyncio.to_thread(load_fias_sync)
        except Exception as e:
            logger.error(f"Ошибка загрузки ФИАС логов: {e}")
            return {}

    def _generate_full_report(self, session_id: str, messages: List[Dict], llm_logs_map: Dict[int, List[Dict]] = None, user_timezone: str = None, fias_logs_map: Dict[int, List[Dict]] = None) -> str:
        """
        Генерирует полный отчет по шаблону ТЗ (2026-01-06).

        ИСПРАВЛЕНО (2026-01-06): Добавлен параметр llm_logs_map для LLM запросов из таблицы
        ИСПРАВЛЕНО (2026-01-19): Добавлен параметр user_timezone для часового пояса пользователя
        """

        channel = messages[0].get('channel', 'unknown') if messages else 'unknown'
        first_msg_time = messages[0].get('created_at') if messages else None
        last_msg_time = messages[-1].get('created_at') if messages else None

        # Канал на русском
        channel_map = {
            'telegram': 'Телеграм',
            'web': 'Веб-чат',
            'test': 'Тестовый канал'
        }
        channel_ru = channel_map.get(channel, channel)

        # ИСПРАВЛЕНО (2026-01-19): Используем переданный timezone или определяем автоматически
        if user_timezone is None:
            user_timezone = self._get_user_timezone_sync(session_id, messages)

        first_msg_time_formatted = self._format_datetime(first_msg_time, user_timezone)
        last_msg_time_formatted = self._format_datetime(last_msg_time, user_timezone)

        # Заголовок отчета
        report = f"""================================================================================
ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА (шаблон BotOrder trace v4.1 - 2026-05-05)
================================================================================
Session ID: {session_id}
Канал: {channel_ru}
Всего сообщений: {len(messages)}
Период: {first_msg_time_formatted} - {last_msg_time_formatted}
Часовой пояс: {user_timezone}

================================================================================
ДЕТАЛЬНАЯ ТРАССИРОВКА ПО ШАГАМ
================================================================================

"""

        # Детальная трассировка каждого сообщения
        for i, msg in enumerate(messages, 1):
            next_msg = messages[i] if i < len(messages) else None
            # ИСПРАВЛЕНО (2026-01-06): Передаем llm_logs_map
            report += self._format_message_details(i, msg, messages[:i], next_msg, llm_logs_map, fias_logs_map)
            report += "\n"

        # Статистика
        report += f"\n{'=' * 80}\n"
        report += "СТАТИСТИКА ДИАЛОГА\n"
        report += f"{'=' * 80}\n"
        report += self._generate_statistics(messages)

        report += "\n"
        report += "=" * 80 + "\n"

        return report

    def _format_between_message_operations(
        self,
        *,
        msg_id: int,
        llm_logs_map: Dict[int, List[Dict]] = None,
        fias_logs_map: Dict[int, List[Dict]] = None,
    ) -> str:
        """Formats operations executed after an inbound user message and before bot reply."""
        operations = []
        fias_calls = (fias_logs_map or {}).get(msg_id, []) or []
        for call in fias_calls:
            operations.append({
                "kind": "fias",
                "created_at": call.get("created_at"),
                "data": call,
            })
        for call in (llm_logs_map or {}).get(msg_id, []) or []:
            operations.append({
                "kind": "llm",
                "created_at": call.get("created_at"),
                "data": call,
            })

        details = "\n4. Технические операции после этой реплики до ответа бота:\n"
        if not operations:
            details += " {(операций не было)}\n"
            return details

        operations.sort(key=lambda item: str(item.get("created_at") or ""))
        total_cost = 0.0

        def payload_preview(value):
            try:
                return json.dumps(value, ensure_ascii=False, default=str, indent=2)
            except Exception:
                return str(value)

        for index, operation in enumerate(operations, 1):
            data = operation["data"]
            if operation["kind"] == "fias":
                details += (
                    f"\n4.{index}. ФИАС id={data.get('id')} | endpoint={data.get('endpoint')} | "
                    f"method={data.get('method')} | status={data.get('http_status')} | "
                    f"duration_ms={data.get('duration_ms')} | stage={data.get('state_stage') or '-'} | "
                    f"error={data.get('error_message') or '-'}\n"
                )
                details += (
                    f" Результат: house_guid={data.get('fias_house_guid') or '-'} | "
                    f"street_guid={data.get('fias_street_guid') or '-'} | "
                    f"local_building_id={data.get('building_id') or '-'}\n"
                )
                details += " Request payload:\n"
                details += payload_preview(data.get("request_payload")) + "\n"
                details += " Response payload:\n"
                details += payload_preview(data.get("response_payload")) + "\n"
                continue

            cost_rub = float(data.get("cost_rub") or 0.0)
            total_cost += cost_rub
            caller_service = data.get("caller_service") or "Unknown"
            prompt_slug = data.get("prompt_slug") or "-"
            provider = data.get("provider") or "unknown"
            model = data.get("model") or "unknown"
            details += (
                f"\n4.{index}. LLM caller_service={caller_service} | prompt_slug={prompt_slug} | "
                f"provider={provider} | model={model} | "
                f"tokens={data.get('total_tokens') or 0} | cost_rub={cost_rub:.4f}\n"
            )
            prompt_text = data.get("prompt_text") or ""
            response_text = data.get("response_text") or ""
            if prompt_text:
                details += " Полный промпт:\n"
                details += f"{prompt_text}\n"
            if response_text:
                details += " Сырой ответ LLM:\n"
                details += f"{response_text}\n"

        next_index = len(operations) + 1
        if not fias_calls:
            details += f"\n4.{next_index}. ФИАС: внешних вызовов ФИАС после этой реплики не было.\n"
            next_index += 1
        details += f"\n4.{next_index}. Стоимость LLM после этой реплики: {total_cost:.4f} рублей\n"
        return details

    def _format_bot_order_state_summary(self, state_snapshot: Dict[str, Any]) -> str:
        if not isinstance(state_snapshot, dict) or not state_snapshot:
            return ""
        lines = []
        address = state_snapshot.get('address_input') or {}
        local_address = state_snapshot.get('local_address') or {}
        service_context = state_snapshot.get('service_context') or {}
        fias_result = state_snapshot.get('fias_result') or {}
        problem = state_snapshot.get('problem') or {}
        contact = state_snapshot.get('contact') or {}

        address_parts = [
            address.get('city') or address.get('settlement'),
            address.get('street'),
            address.get('house'),
        ]
        address_text = ', '.join(str(part) for part in address_parts if part)
        if address_text or local_address or service_context or fias_result:
            lines.append(
                " address="
                + (address_text or address.get('normalized_text') or address.get('raw_text') or '-')
                + f" | status={service_context.get('service_status') or fias_result.get('status') or '-'}"
                + f" | building_id={local_address.get('building_id') or '-'}"
                + f" | service_object_id={service_context.get('service_object_id') or '-'}"
                + f" | company_id={service_context.get('company_id') or '-'}"
            )

        contact_bits = []
        if contact.get('name'):
            contact_bits.append(f"name={contact.get('name')}")
        if contact.get('phone'):
            contact_bits.append(f"phone={contact.get('phone')}")
        if contact_bits or contact.get('status'):
            lines.append(f" contact={'; '.join(contact_bits) if contact_bits else '-'} | status={contact.get('status') or '-'}")

        txt_prb = (problem.get('txtPrb') or '').strip()
        if txt_prb:
            lines.append(f" txtPrb={txt_prb}")

        return ''.join(f" {line}\n" for line in lines)

    def _format_message_details(self, num: int, msg: Dict, previous_messages: List[Dict], next_msg: Dict = None, llm_logs_map: Dict[int, List[Dict]] = None, fias_logs_map: Dict[int, List[Dict]] = None) -> str:
        """Форматирует детали сообщения по шаблону ТЗ (2026-01-06).

        ИСПРАВЛЕНО (2026-01-06): Добавлен параметр llm_logs_map для LLM запросов из таблицы

        Шаблон для User -> Bot (inbound):
        1. Направление
        2. Текст
        3. txtPrb

        Шаблон для Bot -> User (outbound):
        1-9. Все пункты включая микросервисы, фильтры, стоимость
        """

        direction = msg.get('direction', 'unknown')
        text = msg.get('text', '')
        created_at = msg.get('created_at', '')
        channel = msg.get('channel', '')
        msg_id = msg.get('id', '')
        metadata = msg.get('metadata', {})

        # Парсим metadata если это строка
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}

        # Определяем направление
        if direction == 'inbound':
            direction_label = "User -> Bot"
        else:
            direction_label = "Bot -> User"

        # Канал на русском
        channel_map = {
            'telegram': 'Телеграм',
            'web': 'Веб-чат',
            'test': 'Тестовый канал'
        }
        channel_ru = channel_map.get(channel, channel)

        # Извлекаем txtPrb
        txtPrb = ''
        if isinstance(metadata, dict):
            txtPrb = metadata.get('txtPrb', '')
            if not txtPrb:
                service_result = metadata.get('service_result', {})
                if isinstance(service_result, dict):
                    service_metadata = service_result.get('_metadata', {})
                    txtPrb = service_metadata.get('txtPrb', '')

        # Начинаем формировать отчет по шагу
        details = f"""
===== Шаг № {num}=====
1. Направление: {direction_label} ({channel_ru})
2. Текст: {text}
3. txtPrb = {txtPrb if txtPrb else '(нет данных)'}
"""

        # Для User -> Bot - только пункты 1-3
        if direction == 'inbound':
            details += self._format_between_message_operations(
                msg_id=msg_id,
                llm_logs_map=llm_logs_map,
                fias_logs_map=fias_logs_map,
            )
            return details

        # Для Bot -> User - все пункты
        service_result = metadata.get('service_result', {})
        service_metadata = service_result.get('_metadata', {}) if isinstance(service_result, dict) else {}

        target_message_id = msg_id
        if direction == 'outbound' and previous_messages:
            for prev_msg in reversed(previous_messages):
                if prev_msg.get('direction') == 'inbound':
                    target_message_id = prev_msg.get('id')
                    break

        # 4. Состояние выбора услуги
        details += "\n4. Состояние выбора услуги:\n"
        established_filters = service_metadata.get('established_filters', {})
        if isinstance(established_filters, dict) and established_filters:
            filter_order = [
                ('incident_type', 'Тип обращения'),
                ('location_type', 'Локализация'),
                ('category', 'Категория'),
            ]
            printed = False
            for filter_name, label in filter_order:
                if filter_name in established_filters:
                    filter_data = established_filters[filter_name]
                    if isinstance(filter_data, dict):
                        value = filter_data.get('value', 'null')
                        conf_raw = filter_data.get('confidence', 0.0) or 0.0
                        confidence = float(conf_raw) * 100
                        if value == 'null' or value is None:
                            continue
                        else:
                            details += f" {label}: {value} ({confidence:.0f}%)\n"
                            printed = True
            if not printed:
                details += " Пока услуга не определялась или данных недостаточно.\n"
        else:
            details += " Пока услуга не определялась.\n"

        details += "\n5. Состояние оркестратора:\n"
        orchestrator_meta = service_metadata.get('bot_order_orchestrator', {}) if isinstance(service_metadata, dict) else {}
        if orchestrator_meta:
            stage = orchestrator_meta.get('stage')
            details += f" stage={stage} ({self._describe_bot_order_stage(stage)})\n"
        else:
            details += " {(нет данных)}\n"
        state_snapshot = service_metadata.get('state_snapshot', {}) if isinstance(service_metadata, dict) else {}
        state_summary = self._format_bot_order_state_summary(state_snapshot)
        if state_summary:
            details += "\n6. Краткое состояние заявки:\n"
            details += state_summary
            details += "\n7. Технические операции:\n"
        else:
            details += "\n6. Технические операции:\n"
        details += " LLM, ФИАС и другие операции показаны после предыдущего входящего сообщения, до этой реплики бота.\n"
        return details
        fias_calls = []
        fias_log_ids = []
        if isinstance(metadata, dict):
            fias_calls = metadata.get('fias_calls') or []
            fias_log_ids = metadata.get('fias_log_ids') or []
        if not fias_log_ids and isinstance(service_metadata, dict):
            fias_log_ids = service_metadata.get('fias_log_ids') or []
        if fias_logs_map and target_message_id in fias_logs_map:
            fias_calls = fias_logs_map[target_message_id]
        if not fias_log_ids and fias_calls:
            fias_log_ids = [call.get('id') for call in fias_calls if call.get('id')]

        if fias_calls or fias_log_ids:
            def payload_preview(value):
                try:
                    return json.dumps(value, ensure_ascii=False, default=str, indent=2)
                except Exception:
                    return str(value)

            details += "\n6. Вызовы ФИАС:\n"
            details += " Показаны операции, выполненные между предыдущим сообщением пользователя и этим ответом бота.\n"
            if fias_log_ids:
                details += f" IDs: {fias_log_ids}\n"
            if fias_calls:
                for call in fias_calls:
                    details += (
                        f" ФИАС id={call.get('id')} | endpoint={call.get('endpoint')} | "
                        f"method={call.get('method')} | status={call.get('http_status')} | "
                        f"duration_ms={call.get('duration_ms')} | stage={call.get('state_stage') or '-'} | "
                        f"error={call.get('error_message') or '-'}\n"
                    )
                    details += f" Результат: house_guid={call.get('fias_house_guid') or '-'} | street_guid={call.get('fias_street_guid') or '-'} | local_building_id={call.get('building_id') or '-'}\n"
                    details += " Request payload:\n"
                    details += payload_preview(call.get('request_payload')) + "\n"
                    details += " Response payload:\n"
                    details += payload_preview(call.get('response_payload')) + "\n"
            else:
                details += " Подробные записи не приложены к metadata; см. таблицу fias_request_log по IDs выше.\n"
        else:
            state_snapshot = service_metadata.get('state_snapshot', {}) if isinstance(service_metadata, dict) else {}
            local_address = state_snapshot.get('local_address', {}) if isinstance(state_snapshot, dict) else {}
            fias_result = state_snapshot.get('fias_result', {}) if isinstance(state_snapshot, dict) else {}
            details += "\n6. Вызовы ФИАС:\n"
            if local_address or fias_result:
                source = local_address.get('match_source') or '-'
                if source == 'local+fias':
                    details += " Внешнего вызова ФИАС не было: адрес найден в локальной адресной базе, в записи уже сохранены GUID ФИАС.\n"
                else:
                    details += " Внешних вызовов ФИАС между предыдущим сообщением пользователя и этим ответом не было.\n"
                details += (
                    f" Текущее состояние адреса: source={source} | "
                    f"building_id={local_address.get('building_id') or '-'} | "
                    f"street_guid={fias_result.get('fias_street_guid') or '-'} | "
                    f"house_guid={fias_result.get('fias_house_guid') or '-'}\n"
                )
            else:
                details += " Внешних вызовов ФИАС между предыдущим сообщением пользователя и этим ответом не было.\n"

        # 9.1. LLM вызовы (промпты и ответы из таблицы llm_request_log)
        # ИСПРАВЛЕНО (2026-01-06): Берем данные из таблицы llm_request_log вместо metadata
        # ИСПРАВЛЕНО (2026-01-06): Для outbound сообщений берем LLM вызовы от предыдущего inbound
        llm_calls_found = False
        llm_total_cost = 0.0  # Для подсчета общей стоимости
        cost_found = False  # ИСПРАВЛЕНО (2026-01-06): Инициализация переменной

        # Определяем какой message_id искать
        target_message_id = msg_id
        if direction == 'outbound' and previous_messages:
            # Для outbound берем LLM вызовы от предыдущего inbound сообщения
            # ИСПРАВЛЕНО (2026-01-06): Ищем последнее inbound в previous_messages
            for prev_msg in reversed(previous_messages):
                if prev_msg.get('direction') == 'inbound':
                    target_message_id = prev_msg.get('id')
                    break

        if llm_logs_map and target_message_id in llm_logs_map:
            llm_calls = llm_logs_map[target_message_id]
            for llm_call in llm_calls:
                cost_found = True  # ИСПРАВЛЕНО (2026-01-06): Нашлись LLM вызовы
                provider = llm_call.get('provider', 'unknown')
                model = llm_call.get('model', 'unknown')
                prompt_text = llm_call.get('prompt_text', '')
                response_text = llm_call.get('response_text', '')
                total_tokens = llm_call.get('total_tokens', 0)
                cost_rub = float(llm_call.get('cost_rub', 0.0))  # ИСПРАВЛЕНО (2026-01-06): Decimal -> float

                llm_total_cost += cost_rub  # Суммируем стоимость

                if not llm_calls_found:
                    details += "\n7. LLM вызовы (полные промпты и сырые ответы):\n"
                    details += " Показаны операции, выполненные между предыдущим сообщением пользователя и этим ответом бота.\n"
                    llm_calls_found = True

                # ИСПРАВЛЕНО (2026-02-24): Используем service_name из БД
                # ИСПРАВЛЕНО (2026-03-07): Убран весь fallback хардкод по тексту промпта
                caller_service = llm_call.get('caller_service', 'Unknown')
                prompt_slug = llm_call.get('prompt_slug')
                prompt_source = llm_call.get('prompt_source', 'unknown')
                service_name = caller_service
                details += (
                    f" caller_service={caller_service} | "
                    f"prompt_slug={prompt_slug or '-'} | "
                    f"prompt_source={prompt_source}\n"
                )

                if prompt_text:
                    display_model = model
                    service_label = f" Промпт LLM для {service_name} ({provider} - {display_model}) "
                    border_length = len(service_label)
                    details += f"{'=' * border_length}\n{service_label}\n{'=' * border_length}\n"

                    details += f"{prompt_text}\n"

                if response_text:
                    display_model = model
                    service_label = f" Ответ LLM для {service_name} ({provider} - {display_model}) "
                    border_length = len(service_label)
                    details += f"{'=' * border_length}\n{service_label}\n{'=' * border_length}\n"

                    details += f"{response_text}\n"

        if not llm_calls_found:
            details += "\n7. LLM вызовы:\n {(нет данных из llm_request_log)}\n"

        # 10. Стоимость шага
        details += "\n8. Стоимость шага:\n"

        # ИСПРАВЛЕНО (2026-01-06): Берем стоимость из llm_logs_map
        if llm_calls_found and llm_total_cost > 0:
            details += f" Итого: {llm_total_cost:.4f} рублей (из llm_request_log)\n"
        else:
            # Фоллбэк на metadata если данных нет в llm_request_log
            cost_found = False

            # Проверяем service_result._metadata._ai_metadata
            ai_metadata = service_result.get('_ai_metadata') if isinstance(service_result, dict) else None
            if ai_metadata:
                usage = ai_metadata.get('usage', {}) if isinstance(ai_metadata, dict) else {}
                model = ai_metadata.get('model', 'unknown') if isinstance(ai_metadata, dict) else 'unknown'
                if usage:
                    tokens = usage.get('total_tokens', 0)
                    cost = usage.get('cost_rub', 0.0)
                    details += f" {model} = {tokens} токенов, {cost:.4f} рублей\n"
                    cost_found = True

            # Проверяем service_result._metadata (старый формат)
            if not cost_found:
                tokens = service_metadata.get('tokens', 0)
                cost = service_metadata.get('cost', 0) or service_metadata.get('total_cost', 0)
                model = service_metadata.get('model') or service_metadata.get('llm_model', 'unknown')
                if tokens or cost:
                    details += f" {model} = {tokens} токенов, {cost:.4f} рублей\n"
                    cost_found = True

        if not cost_found:
            details += " {(данные о стоимости отсутствуют)}\n"

        return details

    def _describe_bot_order_stage(self, stage: str) -> str:
        descriptions = {
            "ingress_normalize": "получено новое сообщение, идет нормализация входа",
            "greeting": "бот ответил на приветствие и ждет адрес/проблему",
            "address_pipeline": "идет извлечение и проверка адреса",
            "address_incomplete": "адрес неполный, бот ждет недостающую часть",
            "address_not_found": "адрес не найден, бот ждет уточнение адреса",
            "address_not_serviced": "дом найден, но не обслуживается активной компанией",
            "problem_required": "адрес найден, бот ждет описание проблемы",
            "service_selection": "идет определение услуги",
            "need_service_type_clarification": "не выбран тип обращения, задан уточняющий вопрос",
            "need_localization_clarification": "нужно уточнить, где именно проявилась проблема, чтобы выбрать индивидуальное или общедомовое имущество",
            "need_category_clarification": "не выбрана категория, задан уточняющий вопрос",
            "service_confirmation": "услуга выбрана, бот ждет подтверждение пользователя",
            "order_create": "создается заявка",
            "security_guard_blocked": "защитник остановил небезопасный запрос",
        }
        return descriptions.get(stage or "", "служебный этап нового оркестратора")

    def _format_metadata_v2(self, metadata: Any, previous_messages: List[Dict], indent: str = "  ") -> str:
        """Улучшенное форматирование METADATA с подробной расшифровкой."""

        # Парсим metadata если это строка
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}

        if not isinstance(metadata, dict):
            return "(нет метаданных)"

        lines = []

        # 1. service_detection с подробной расшифровкой
        if 'service_detection' in metadata or 'service_result' in metadata:
            lines.append("┌─── SERVICE DETECTION ───")
            service_result = metadata.get('service_result') or metadata.get('service_detection', {})

            if isinstance(service_result, dict):
                status = service_result.get('status', 'unknown')
                message = service_result.get('message', '')
                # ИСПРАВЛЕНО (2025-12-29): Перевод статуса на русский
                status_translated = self._translate_status(status)
                lines.append(f"│ Status: {status_translated} ({status})")
                lines.append(f"│ Message: {message}")

                # ДОБАВЛЕНО: Результаты микросервисов из microservices_results
                # microservices_results может быть как в service_result._metadata так и прямо в service_result
                microservices_results = service_result.get('microservices_results') or service_result.get('_metadata', {}).get('microservices_results', {})

                if microservices_results:
                    lines.append("")
                    lines.append("├─ МИКРОСЕРВИСЫ (результаты поиска):")
                    lines.append("│")

                    # Выводим каждый микросервис
                    for ms_name, ms_result in microservices_results.items():
                        if isinstance(ms_result, dict) and ms_result.get('candidates'):
                            lines.append(f"│ {ms_name.upper()}:")
                            for cand in ms_result['candidates']:
                                service_id = cand.get('service_id', '?')
                                service_name = cand.get('service_name', 'Unknown')
                                confidence = cand.get('confidence', 0.0)
                                lines.append(f"│   - ID:{service_id} | {service_name} | {confidence*100:.1f}%")
                            lines.append("│")

                # Candidates с разрезом по микросервисам
                candidates = service_result.get('candidates', [])
                if candidates and not microservices_results:
                    lines.append("")
                    lines.append("├─ CANDIDATES (по источникам):")
                    lines.append("│")

                    # Группируем по source
                    by_source = {}
                    for candidate in candidates:
                        if isinstance(candidate, dict):
                            sources = candidate.get('sources', ['unknown'])
                            source = sources[0] if sources else 'unknown'
                            if source not in by_source:
                                by_source[source] = []
                            by_source[source].append(candidate)

                    # Выводим каждый микросервис
                    for source, source_candidates in by_source.items():
                        lines.append(f"│ {source}:")
                        for cand in source_candidates:
                            service_id = cand.get('service_id', '?')
                            service_name = cand.get('service_name', 'Unknown')
                            confidence = cand.get('confidence', 0.0)
                            lines.append(f"│   - ID:{service_id} | {service_name} | {confidence*100:.1f}%")

                    lines.append("│")

                # accumulated_fields
            acc_fields = service_result.get('_metadata', {}).get('accumulated_fields', {})
            if acc_fields:
                lines.append("")
                lines.append("├─ ACCUMULATED FIELDS:")
                lines.append("│ (накопленная информация из диалога - location, source, problem, etc)")
                lines.append("│")
                for key, value in acc_fields.items():
                    if value:
                        lines.append(f"│   {key}: {value}")
                lines.append("│")

            # ИСПРАВЛЕНО (2025-12-29): Второй проход с фильтрами
            second_pass = service_result.get('_metadata', {}).get('second_pass', {})
            if second_pass and second_pass.get('enabled'):
                lines.append("")
                lines.append("├─ ВТОРОЙ ПРОХОД (фильтрация кандидатов):")
                lines.append("│")
                lines.append(f"│ До фильтрации: {second_pass.get('before_count', 0)} кандидатов")
                lines.append(f"│ После фильтрации: {second_pass.get('after_count', 0)} кандидатов")

                applied_filters = second_pass.get('applied_filters', {})
                if applied_filters:
                    lines.append("│")
                    lines.append("│ Примененные фильтры:")
                    for key, value in applied_filters.items():
                        if value:
                            lines.append(f"│   - {key}: {value}")

                lines.append("│")

                # established_filters
                est_filters = service_result.get('_metadata', {}).get('established_filters', {})
                if est_filters:
                    lines.append("")
                    lines.append("├─ ESTABLISHED FILTERS:")
                    lines.append("│ (установленные фильтры для сокращения списка кандидатов)")
                    lines.append("│")
                    for key, value in est_filters.items():
                        if isinstance(value, dict) and 'value' in value:
                            conf = value.get('confidence', 0.0)
                            lines.append(f"│   - {key}: {value['value']} (confidence: {conf*100:.0f}%)")
                        elif value:
                            lines.append(f"│   - {key}: {value}")
                    lines.append("│")

                # ДОБАВЛЕНО: FilterDetectionService промты и результаты
                filter_detection = service_result.get('_metadata', {}).get('filter_detection', {})
                if filter_detection:
                    lines.append("")
                    lines.append("├─ FILTER DETECTION SERVICE (LLM):")
                    lines.append("│")

                    # Status
                    status = filter_detection.get('status', 'unknown')
                    # ИСПРАВЛЕНО (2025-12-29): Перевод статуса на русский
                    status_translated = self._translate_status(status)
                    lines.append(f"│ Status: {status_translated} ({status})")

                    # Filters
                    filters = filter_detection.get('filters', {})
                    if filters:
                        lines.append("│")
                        lines.append("│ Определенные фильтры:")
                        for key, value in filters.items():
                            if value:
                                lines.append(f"│   - {key}: {value}")

                    # Confidence
                    confidence = filter_detection.get('confidence', 0.0)
                    if confidence:
                        lines.append(f"│")
                        lines.append(f"│ Confidence: {confidence*100:.0f}%")

                    # Prompt
                    prompt = filter_detection.get('prompt', '')
                    if prompt:
                        lines.append("│")
                        lines.append("│ Prompt FilterDetectionService:")
                        lines.append("│ ─" + "─" * 76)
                        # Обрезаем слишком длинный промт для читаемости
                        prompt_lines = prompt.split('\n')
                        for line in prompt_lines[:30]:  # Первые 30 строк
                            lines.append(f"│ {line}")
                        if len(prompt_lines) > 30:
                            lines.append(f"│ ... ({len(prompt_lines) - 30} строк пропущено)")
                        lines.append("│ ─" + "─" * 76)

                    # LLM Response
                    llm_response = filter_detection.get('llm_response', '')
                    if llm_response:
                        lines.append("│")
                        lines.append("│ Response FilterDetectionService:")
                        lines.append(f"│ {llm_response}")

                    # Parsed Response
                    parsed_response = filter_detection.get('parsed_response', {})
                    if parsed_response:
                        lines.append("│")
                        lines.append("│ Parsed response:")
                        for key, value in parsed_response.items():
                            if value:
                                lines.append(f"│   {key}: {value}")

                    lines.append("│")

                # ДОБАВЛЕНО: AI Orchestrator результаты
                ai_orchestrator = service_result.get('_metadata', {}).get('ai_orchestrator', {})
                if ai_orchestrator:
                    lines.append("")
                    lines.append("├─ AI ORCHESTRATOR:")
                    lines.append("│")

                    # Status
                    status = ai_orchestrator.get('status', 'unknown')
                    # ИСПРАВЛЕНО (2025-12-29): Перевод статуса на русский
                    status_translated = self._translate_status(status)
                    lines.append(f"│ Status: {status_translated} ({status})")

                    # Service ID Рё Name
                    service_id = ai_orchestrator.get('service_id')
                    service_name = ai_orchestrator.get('service_name')
                    if service_id:
                        lines.append(f"│")
                        lines.append(f"│ Service ID: {service_id}")
                    if service_name:
                        lines.append(f"│ Service Name: {service_name}")

                    # Confidence
                    confidence = ai_orchestrator.get('confidence', 0.0)
                    if confidence:
                        lines.append(f"│")
                        lines.append(f"│ Confidence: {confidence*100:.0f}%")

                    # ИСПРАВЛЕНО (2025-12-29): Таблица кандидатов вместо счетчика
                    # Берем кандидатов из service_result.candidates
                    candidates = service_result.get('candidates', [])
                    if candidates:
                        lines.append(f"│")
                        lines.append(f"│ ТАБЛИЦА КАНДИДАТОВ:")
                        lines.append(f"│ ┌────────┬───────────────────────────────┬───────────┐")
                        lines.append(f"│ │ ID     │ Название                      │ Вероятн.  │")
                        lines.append(f"│ ├────────┼───────────────────────────────┼───────────┤")

                        for cand in candidates[:15]:  # До 15 кандидатов
                            cid = cand.get('service_id', '?')
                            name = cand.get('service_name', cand.get('scenario_name', 'Unknown'))[:30]
                            conf = cand.get('confidence', 0.0) * 100
                            lines.append(f"│ │ {cid:<6} │ {name:<30} │ {conf:>6.1f}% │")

                        if len(candidates) > 15:
                            lines.append(f"│ │ ...    │ (... еще {len(candidates) - 15})        │           │")

                        lines.append(f"│ └────────┴───────────────────────────────┴───────────┘")

                    # Message
                    message = ai_orchestrator.get('message', '')
                    if message:
                        lines.append(f"│")
                        lines.append(f"│ Message: {message}")

                    # Reasoning
                    reasoning = ai_orchestrator.get('reasoning', '')
                    if reasoning:
                        lines.append(f"│")
                        lines.append("│ Reasoning:")
                        lines.append("│ ─" + "─" * 76)
                        reasoning_lines = reasoning.split('\n')
                        for line in reasoning_lines[:20]:  # Первые 20 строк
                            lines.append(f"│ {line}")
                        if len(reasoning_lines) > 20:
                            lines.append(f"│ ... ({len(reasoning_lines) - 20} строк пропущено)")
                        lines.append("│ ─" + "─" * 76)

                    lines.append("│")

                # ДОБАВЛЕНО (2025-12-29): AI Agent промпты и ответы (генерация вопросов)
                ai_metadata = service_result.get('_ai_metadata')
                if ai_metadata:
                    lines.append("")
                    lines.append("├─ AI AGENT SERVICE (генерация вопросов):")
                    lines.append("│")

                    # Model
                    model = ai_metadata.get('model', 'unknown')
                    if model:
                        lines.append(f"│ Model: {model}")

                    # Usage
                    usage = ai_metadata.get('usage', {})
                    if usage:
                        total_tokens = usage.get('total_tokens', 0)
                        cost = usage.get('cost_rub', 0.0)
                        if total_tokens:
                            lines.append(f"│ Tokens: {total_tokens}")
                        if cost:
                            lines.append(f"│ Cost: {cost:.4f} RUB")

                    # Prompt
                    prompt = ai_metadata.get('prompt', '')
                    if prompt:
                        lines.append("│")
                        lines.append("│ Prompt AIAgentService:")
                        lines.append("│ ─" + "─" * 76)
                        # Обрезаем слишком длинный промт для читаемости
                        prompt_lines = prompt.split('\n')
                        for line in prompt_lines[:40]:  # Первые 40 строк
                            lines.append(f"│ {line}")
                        if len(prompt_lines) > 40:
                            lines.append(f"│ ... ({len(prompt_lines) - 40} строк пропущено)")
                        lines.append("│ ─" + "─" * 76)

                    # Response
                    response = ai_metadata.get('response', '')
                    if response:
                        lines.append("│")
                        lines.append("│ Response AIAgentService:")
                        lines.append(f"│ {response}")

                    lines.append("│")

            lines.append("└─────────────────────────")
            lines.append("")

        # 2. Остальные metadata
        for key, value in metadata.items():
            if key in ['service_detection', 'service_result', 'txtPrb']:
                continue
            if key == 'auto_greeting' and value:
                lines.append(f"auto_greeting: True")
            elif key not in ['username', 'first_name', 'last_name']:
                lines.append(f"{key}: {value}")

        return '\n'.join(lines) if lines else "(нет метаданных)"

    def _analyze_message_significance(self, text: str, metadata: Dict, previous_messages: List[Dict]) -> str:
        """Анализирует значимость входящего сообщения."""

        analysis = []

        # Проверяем txtPrb
        txtPrb = metadata.get('txtPrb', '') if isinstance(metadata, dict) else ''

        # Проверяем что именно сказано
        text_lower = text.lower()

        # Определяем тип информации
        has_location = any(word in text_lower for word in ['зал', 'кухн', 'ванной', 'спальн', 'коридор', 'комнат'])
        has_object = any(word in text_lower for word in ['труб', 'батарей', 'кран', 'радиатор', 'лифт'])
        has_problem = any(word in text_lower for word in ['теч', 'льет', 'капает', 'протека', 'сломал', 'не работ'])

        if has_problem or has_object or has_location or txtPrb:
            analysis.append("┌─── АНАЛИЗ СООБЩЕНИЯ ───")
            analysis.append("│")
            analysis.append("├─ ЗНАЧИМАЯ ИНФОРМАЦИЯ:")

            if has_problem:
                analysis.append("│ [+] Проблема: обнаружена (течь/сломано)")
            if has_object:
                analysis.append("│ [+] Объект: указан (труба/батарея/и т.д.)")
            if has_location:
                analysis.append("│ [+] Локация: указана (зал/кухня/и т.д.)")

            # Проверяем накопленную информацию из предыдущих сообщений
            prev_problem = None
            for prev_msg in reversed(previous_messages):
                if prev_msg.get('direction') == 'inbound':
                    prev_text = prev_msg.get('text', '').lower()
                    if any(word in prev_text for word in ['теч', 'льет', 'капает']):
                        prev_problem = "течь"
                        break

            if prev_problem:
                analysis.append("│")
                analysis.append("├─ КОНТЕКСТ (из предыдущих сообщений):")
                analysis.append(f"│ [+] Известно: {prev_problem}")

            analysis.append("│")
            analysis.append("└─ ЗАКЛЮЧЕНИЕ:")
            analysis.append("[+] Сообщение содержит ЗНАЧИМУЮ информацию")
            analysis.append("   - Установлены детали проблемы")
        else:
            analysis.append("[!] Входящее сообщение не содержит значимой информации")

        return '\n'.join(analysis)

    def _analyze_bot_response(self, metadata: Dict) -> str:
        """Анализирует ответ бота.

        ИСПРАВЛЕНО (2025-12-29): Добавлен перевод статусов на русский.
        ИСПРАВЛЕНО (2025-12-29): Добавлено описание логики уточнения для AMBIGUOUS.
        """

        service_result = metadata.get('service_result') or metadata.get('service_detection', {})

        if not isinstance(service_result, dict):
            return "[?] Статус обработки: unknown"

        status = service_result.get('status', 'unknown')
        status_translated = self._translate_status(status)

        if status == 'SUCCESS':
            service_name = service_result.get('service_name', 'неизвестно')
            return f"[+] {status_translated}: {service_name}"
        elif status == 'AMBIGUOUS':
            candidates = service_result.get('candidates', [])
            result = f"[!] {status_translated}. Найдено кандидатов: {len(candidates)}\n"

            # ИСПРАВЛЕНО (2025-12-29): Добавляем описание что уточняем
            result += "\n📋 ЧТО БУДЕМ УТОЧНЯТЬ:\n"

            # Анализируем установленные фильтры
            established_filters = service_result.get('_metadata', {}).get('established_filters', {})

            # Проверяем какие фильтры НЕ установлены
            missing_filters = []
            if not any(f.get('location_type') for f in [established_filters]):
                missing_filters.append("Локация: неизвестна (Индивидуальное vs Общедомовое)")

            if not any(f.get('category') for f in [established_filters]):
                missing_filters.append("Категория: неизвестна (Водоснабжение, Отопление и т.д.)")

            if not any(f.get('incident_type') for f in [established_filters]):
                missing_filters.append("Тип: неизвестен (Инцидент vs Запрос)")

            if not missing_filters:
                missing_filters.append("Детали проблемы: недостаточно информации")

            for mf in missing_filters:
                result += f"- {mf}\n"

            # Объяснение почему
            result += "\n⚠️ ПОЧЕМУ:\n"
            result += f"- После фильтрации осталось {len(candidates)} кандидатов\n"
            result += "- Нужно сократить список до 1 услуги\n"

            return result
        elif status == 'NOT_FOUND':
            return f"[-] {status_translated}. Требуется уточнение проблемы"
        else:
            return f"[?] {status_translated} ({status})"

    def _generate_statistics(self, messages: List[Dict]) -> str:
        """Генерирует статистику диалога.

        ИСПРАВЛЕНО (2025-12-28): Добавлен блок мониторинга расходов LLM
        """
        inbound_count = sum(1 for m in messages if m.get('direction') == 'inbound')
        outbound_count = sum(1 for m in messages if m.get('direction') == 'outbound')

        # Извлекаем txtPrb из последнего сообщения
        final_txtPrb = ""
        for msg in reversed(messages):
            metadata = msg.get('metadata', {})

            # Парсим metadata если это строка
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}

            if isinstance(metadata, dict):
                txtPrb = metadata.get('txtPrb', '')
                if not txtPrb:
                    service_result = metadata.get('service_result', {})
                    if isinstance(service_result, dict):
                        service_metadata = service_result.get('_metadata', {})
                        txtPrb = service_metadata.get('txtPrb', '')

                if txtPrb:
                    final_txtPrb = txtPrb
                    break

        # ИСПРАВЛЕНО (2025-12-28): Мониторинг расходов LLM
        llm_cost_tracking = self._extract_llm_costs(messages)

        stats = f"""
Всего сообщений: {len(messages)}
  - Входящих (пользователь): {inbound_count}
  - Исходящих (бот): {outbound_count}

Финальное описание проблемы (txtPrb):
{final_txtPrb if final_txtPrb else '(РЅРµ РЅР°РєРѕРїР»РµРЅРѕ)'}

Канал связи: {messages[0].get('channel', 'unknown') if messages else 'unknown'}
"""

        # ИСПРАВЛЕНО (2025-12-28): Добавляем блок расходов если есть данные
        if llm_cost_tracking:
            stats += f"""
{'=' * 80}
💰 МОНИТОРИНГ РАСХОДОВ LLM
{'=' * 80}
{llm_cost_tracking}
{'=' * 80}
"""

        return stats

    def _extract_llm_costs(self, messages: List[Dict]) -> str:
        """
        Извлекает информацию о расходах LLM из metadata сообщений.

        ИСПРАВЛЕНО (2025-12-28): Добавлено для мониторинга расходов
        """
        total_cost = 0.0
        total_tokens = 0
        lite_requests = 0
        pro_requests = 0
        lite_cost = 0.0
        pro_cost = 0.0
        model_usage = {}

        for msg in messages:
            metadata = msg.get('metadata', {})

            # Парсим metadata если это строка
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    continue

            if not isinstance(metadata, dict):
                continue

            # Ищем информацию о расходах в service_result._metadata
            service_result = metadata.get('service_result', {})
            if isinstance(service_result, dict):
                service_metadata = service_result.get('_metadata', {})
                if isinstance(service_metadata, dict):
                    # Проверяем разные возможные поля с расходами
                    # 1. Прямое поле cost
                    cost = service_metadata.get('cost') or service_metadata.get('total_cost')
                    if cost:
                        total_cost += float(cost)

                    # 2. Токены
                    tokens = service_metadata.get('tokens') or service_metadata.get('total_tokens')
                    if tokens:
                        total_tokens += int(tokens)

                    # 3. Информация о модели
                    model = service_metadata.get('model') or service_metadata.get('llm_model')
                    if model:
                        if model not in model_usage:
                            model_usage[model] = {'requests': 0, 'tokens': 0, 'cost': 0.0}
                        model_usage[model]['requests'] += 1

                        if tokens:
                            model_usage[model]['tokens'] += int(tokens)
                        if cost:
                            model_usage[model]['cost'] += float(cost)

                        # Считаем по типам моделей
                        if 'pro' in model.lower():
                            pro_requests += 1
                            pro_cost += float(cost) if cost else 0.0
                        else:
                            lite_requests += 1
                            lite_cost += float(cost) if cost else 0.0

        # Формируем отчет
        if total_cost == 0 and total_tokens == 0:
            return ""  # Нет данных о расходах

        report = []
        report.append(f"Общая стоимость: {total_cost:.2f} руб")
        report.append(f"Всего токенов: {total_tokens}")
        report.append("")

        if lite_requests > 0 or pro_requests > 0:
            report.append("Распределение по моделям:")
            if lite_requests > 0:
                report.append(f"  - YandexGPT Lite: {lite_requests} запросов, {lite_cost:.2f} руб")
            if pro_requests > 0:
                report.append(f"  - YandexGPT Pro: {pro_requests} запросов, {pro_cost:.2f} руб")
            report.append("")

        if model_usage:
            report.append("Детализация по моделям:")
            for model, stats in sorted(model_usage.items()):
                report.append(f"  {model}:")
                report.append(f"    - Запросов: {stats['requests']}")
                if stats['tokens'] > 0:
                    report.append(f"    - Токенов: {stats['tokens']}")
                if stats['cost'] > 0:
                    report.append(f"    - Стоимость: {stats['cost']:.2f} руб")

        return "\n".join(report)


# Удобная функция для быстрого вызова
async def generate_dialog_trace(session_id: str, output_path: str = None) -> str:
    """Быстрая генерация трассировки диалога."""
    service = TraceReportService()
    return await service.generate_trace_report(session_id, output_path=output_path)


if __name__ == '__main__':
    import sys
    import os
    import django

    # Инициализируем Django
    sys.path.insert(0, '/var/www/komunal-dom_ru')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
    django.setup()

    import asyncio

    async def main():
        if len(sys.argv) > 1:
            session_id = sys.argv[1]
            service = TraceReportService()
            path = await service.generate_trace_report(session_id)
            print(f"\n[+] Отчет создан: {path}")
        else:
            print("Использование: python trace_report_service.py <session_id>")

    asyncio.run(main())
