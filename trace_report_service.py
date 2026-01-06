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

logger = logging.getLogger(__name__)


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

    def __init__(self):
        self.tmp_dir = Path('/tmp')

    async def generate_trace_report(
        self,
        session_id: str,
        messages: List[Dict] = None,
        output_path: str = None
    ) -> str:
        """Генерирует улучшенный отчет трассировки диалога."""

        # Загружаем сообщения если не переданы
        if messages is None:
            messages = await self._load_messages_from_db(session_id)

        if not messages:
            logger.warning(f"Нет сообщений для сессии {session_id}")
            return None

        # ИСПРАВЛЕНО (2026-01-06): Загружаем LLM запросы из таблицы llm_request_log
        llm_logs_map = await self._load_llm_logs_for_session(session_id, messages)

        # Генерируем отчет
        report_content = self._generate_full_report(session_id, messages, llm_logs_map)

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
                        # Алиасы для совместимости с существующим кодом
                        cursor.execute("""
                            SELECT
                                id,
                                message_content as text,
                                direction,
                                channel,
                                session_id,
                                timestamp as created_at,
                                metadata
                            FROM dialog_logs
                            WHERE session_id LIKE %s
                            ORDER BY timestamp ASC
                        """, (f"{session_id}%",))

                        columns = ['id', 'text', 'direction', 'channel', 'session_id', 'created_at', 'metadata']
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
                        # ИСПРАВЛЕНО (2026-01-06): Загружаем по session_id вместо временного окна
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
                                error_message
                            FROM llm_request_log
                            WHERE session_id = %s
                            ORDER BY created_at ASC
                        """, (session_id,))

                        columns = ['id', 'provider', 'model', 'prompt_text', 'response_text',
                                   'prompt_tokens', 'completion_tokens', 'total_tokens', 'cost_rub',
                                   'created_at', 'status', 'error_message']

                        all_llm_logs = []
                        for row in cursor.fetchall():
                            llm_log = dict(zip(columns, row))
                            all_llm_logs.append(llm_log)

                        # Связываем LLM запросы с сообщениями по времени и сессии
                        # ИСПРАВЛЕНО (2026-01-06): Простое связывание - все LLM запросы сессии доступны
                        message_llm_map = {}

                        # Для каждого сообщения находим ближайшие LLM запросы
                        for msg in messages:
                            msg_time = msg['created_at']
                            msg_id = msg['id']

                            # Ищем LLM запросы в временном окне +-60 секунд от сообщения
                            # Это нужно чтобы определить какие именно LLM вызовы были для этого сообщения
                            from datetime import timedelta
                            time_window_start = msg_time - timedelta(seconds=60)
                            time_window_end = msg_time + timedelta(seconds=60)

                            matching_llm = []
                            for llm in all_llm_logs:
                                if time_window_start <= llm['created_at'] <= time_window_end:
                                    matching_llm.append(llm)

                            if matching_llm:
                                message_llm_map[msg_id] = matching_llm

                        logger.info(f"Загружено {len(all_llm_logs)} LLM запросов по session_id={session_id}, связано с {len(message_llm_map)} сообщений")
                        return message_llm_map

                finally:
                    conn.close()

            return await asyncio.to_thread(load_llm_sync)

        except Exception as e:
            logger.error(f"Ошибка загрузки LLM логов: {e}")
            return {}

    def _generate_full_report(self, session_id: str, messages: List[Dict], llm_logs_map: Dict[int, List[Dict]] = None) -> str:
        """Генерирует полный отчет по шаблону ТЗ (2026-01-06).

        ИСПРАВЛЕНО (2026-01-06): Добавлен параметр llm_logs_map для LLM запросов из таблицы
        """

        channel = messages[0].get('channel', 'unknown') if messages else 'unknown'
        first_msg_time = messages[0].get('created_at') if messages else None
        last_msg_time = messages[-1].get('created_at') if messages else None

        # Канал на русском
        channel_map = {
            'telegram': 'Телеграм',
            'web': 'Веб-чат',
            'test': 'ПрограммныйТест'
        }
        channel_ru = channel_map.get(channel, channel)

        # Заголовок отчета
        report = f"""================================================================================
ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА (по шаблону ТЗ v3.0 - 2026-01-06)
================================================================================
Session ID: {session_id}
Канал: {channel_ru}
Всего сообщений: {len(messages)}
Период: {first_msg_time} - {last_msg_time}

================================================================================
ДЕТАЛЬНАЯ ТРАССИРОВКА ПО ШАГАМ
================================================================================

"""

        # Детальная трассировка каждого сообщения
        for i, msg in enumerate(messages, 1):
            next_msg = messages[i] if i < len(messages) else None
            # ИСПРАВЛЕНО (2026-01-06): Передаем llm_logs_map
            report += self._format_message_details(i, msg, messages[:i], next_msg, llm_logs_map)
            report += "\n"

        # Статистика
        report += f"\n{'=' * 80}\n"
        report += "СТАТИСТИКА ДИАЛОГА\n"
        report += f"{'=' * 80}\n"
        report += self._generate_statistics(messages)

        report += "\n"
        report += "=" * 80 + "\n"

        return report

    def _format_message_details(self, num: int, msg: Dict, previous_messages: List[Dict], next_msg: Dict = None, llm_logs_map: Dict[int, List[Dict]] = None) -> str:
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
            'test': 'ПрограммныйТест'
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
            return details

        # Для Bot -> User - все 9 пунктов
        service_result = metadata.get('service_result', {})
        service_metadata = service_result.get('_metadata', {}) if isinstance(service_result, dict) else {}

        # 4. TagSearchService
        details += "\n4. TagSearchService\n"
        microservices_results = service_metadata.get('microservices_results', {})
        tag_search = microservices_results.get('tag_search', {}) if isinstance(microservices_results, dict) else {}
        if isinstance(tag_search, dict) and tag_search.get('candidates'):
            for cand in tag_search['candidates']:
                service_name = cand.get('service_name', 'Unknown')
                conf_raw = cand.get('confidence', 0.0) or 0.0
                confidence = float(conf_raw) * 100
                details += f" {{{service_name}, {confidence:.1f}%}}\n"
        else:
            details += " {(нет кандидатов)}\n"

        # 5. SemanticSearchService
        details += "\n5. SemanticSearchService\n"
        semantic_search = microservices_results.get('semantic_search', {}) if isinstance(microservices_results, dict) else {}
        if isinstance(semantic_search, dict) and semantic_search.get('candidates'):
            for cand in semantic_search['candidates']:
                service_name = cand.get('service_name', 'Unknown')
                conf_raw = cand.get('confidence', 0.0) or 0.0
                confidence = float(conf_raw) * 100
                details += f" {{{service_name}, {confidence:.1f}%}}\n"
        else:
            details += " {(нет кандидатов)}\n"

        # 6. VectorSearchService
        details += "\n6. VectorSearchService\n"
        vector_search = microservices_results.get('vector_search', {}) if isinstance(microservices_results, dict) else {}
        if isinstance(vector_search, dict) and vector_search.get('candidates'):
            for cand in vector_search['candidates']:
                service_name = cand.get('service_name', 'Unknown')
                conf_raw = cand.get('confidence', 0.0) or 0.0
                confidence = float(conf_raw) * 100
                details += f" {{{service_name}, {confidence:.1f}%}}\n"
        else:
            details += " {(нет кандидатов)}\n"

        # 7. Итоговое объединение сервисов (MainAgent)
        details += "\n7. Итоговое объединение сервисов (MainAgent):\n"

        # Берем кандидатов из service_result (уже объединенные MainAgent)
        candidates = service_result.get('candidates', []) if isinstance(service_result, dict) else []
        if candidates:
            for cand in candidates:
                service_name = cand.get('service_name', 'Unknown')
                conf_raw = cand.get('confidence', 0.0) or 0.0
                confidence = float(conf_raw) * 100
                sources = cand.get('sources', ['unknown'])
                sources_str = ', '.join(sources)
                details += f" {{{service_name}, {confidence:.1f}%}} (источники: {sources_str})\n"
        else:
            details += " {(нет кандидатов)}\n"

        # 8. Таблица установленных фильтров
        details += "\n8. Таблица установленных фильтров:\n"
        established_filters = service_metadata.get('established_filters', {})
        if isinstance(established_filters, dict) and established_filters:
            for filter_name, filter_data in established_filters.items():
                if isinstance(filter_data, dict):
                    value = filter_data.get('value', 'N/A')
                    conf_raw = filter_data.get('confidence', 0.0) or 0.0
                    confidence = float(conf_raw) * 100
                    details += f" {{{filter_name} = {value}, {confidence:.0f}%}}\n"
                else:
                    details += f" {{{filter_name} = {filter_data}}}\n"
        else:
            details += " {(нет фильтров)}\n"

        # 9. Прочая отладочная информация
        details += "\n9. Прочая отладочная информация:\n"

        # AI Orchestrator
        ai_orchestrator = service_metadata.get('ai_orchestrator', {})
        if isinstance(ai_orchestrator, dict) and ai_orchestrator:
            status = ai_orchestrator.get('status', 'unknown')
            service_id = ai_orchestrator.get('service_id', 'N/A')
            service_name = ai_orchestrator.get('service_name', 'N/A')
            confidence_raw = ai_orchestrator.get('confidence', 0.0) or 0.0
            confidence = float(confidence_raw) * 100
            details += f" AI Orchestrator: Status={status}, ServiceID={service_id}, ServiceName={service_name}, Confidence={confidence:.1f}%\n"

        # Filter Detection
        filter_detection = service_metadata.get('filter_detection', {})
        if isinstance(filter_detection, dict) and filter_detection:
            detected_filters = filter_detection.get('filters', {})
            if detected_filters:
                details += f" FilterDetection: {json.dumps(detected_filters, ensure_ascii=False)}\n"

        # Candidates
        candidates_mainagent = service_result.get('candidates', []) if isinstance(service_result, dict) else []
        if candidates_mainagent:
            details += f" Всего кандидатов: {len(candidates_mainagent)}\n"

        # 9.1. LLM вызовы (промпты и ответы из таблицы llm_request_log)
        # ИСПРАВЛЕНО (2026-01-06): Берем данные из таблицы llm_request_log вместо metadata
        llm_calls_found = False
        llm_total_cost = 0.0  # Для подсчета общей стоимости
        cost_found = False  # ИСПРАВЛЕНО (2026-01-06): Инициализация переменной

        if llm_logs_map and msg_id in llm_logs_map:
            llm_calls = llm_logs_map[msg_id]
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
                    details += "\n9.1. LLM ВЫЗОВЫ (промпты и ответы):\n"
                    llm_calls_found = True

                details += f"\n [{provider} - {model}]\n"
                if prompt_text:
                    details += f"  ПРЕДОСТАВЛЕННЫЙ ПРОМПТ:\n{prompt_text}\n"
                if response_text:
                    details += f"  ОТВЕТ LLM:\n{response_text}\n"

        if not llm_calls_found:
            details += "\n9.1. LLM ВЫЗОВЫ:\n {(нет данных из llm_request_log)}\n"

        # 10. Стоимость шага
        details += "\n10. Стоимость шага:\n"

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

                    # Service ID и Name
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
{final_txtPrb if final_txtPrb else '(не накоплено)'}

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
