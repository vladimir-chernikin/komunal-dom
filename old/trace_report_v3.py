"""
TraceReportService v3.0 - Новый формат трассировки диалогов

ИСПРАВЛЕНО (2026-01-05):
- Обновлено под dialog_logs (message_content, timestamp)
- Новый формат отчета по шагам
- Раздельные блоки для User->Bot и Bot->User
- Стоимость шагов

Шаг User->Bot: только пункты 1-3
Шаг Bot->User: все 9 пунктов

Использование:
    from trace_report_v3 import TraceReportServiceV3
    service = TraceReportServiceV3()
    report = await service.generate_trace_report(session_id='web_123')
"""

import logging
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class TraceReportServiceV3:
    """Сервис для генерации отчетов трассировки диалогов (v3.0)."""

    def __init__(self):
        self.tmp_dir = Path('/tmp')

    async def generate_trace_report(
        self,
        session_id: str,
        messages: List[Dict] = None
    ) -> str:
        """
        Генерирует отчет трассировки в памяти (без файла)

        Returns:
            str: Текст отчета
        """

        # Загружаем сообщения если не переданы
        if messages is None:
            messages = await self._load_messages_from_db(session_id)

        if not messages:
            logger.warning(f"Нет сообщений для сессии {session_id}")
            return f"# ОШИБКА: Нет сообщений для сессии {session_id}"

        # Генерируем отчет
        report_content = self._generate_full_report(session_id, messages)

        return report_content

    async def _load_messages_from_db(self, session_id: str) -> List[Dict]:
        """Загружает сообщения из БД (dialog_logs)."""
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
                        # ИСПРАВЛЕНО (2026-01-05): Используем message_content и timestamp
                        cursor.execute("""
                            SELECT
                                id,
                                direction,
                                message_content,
                                timestamp,
                                channel,
                                user_id,
                                session_id,
                                metadata,
                                message_type,
                                llm_provider,
                                llm_model,
                                tokens_used,
                                cost_rub
                            FROM dialog_logs
                            WHERE session_id = %s
                            ORDER BY timestamp ASC
                        """, [session_id])

                        columns = [desc[0] for desc in cursor.description]
                        messages = []
                        for row in cursor.fetchall():
                            msg = dict(zip(columns, row))
                            # Парсим metadata если это строка
                            if isinstance(msg.get('metadata'), str):
                                try:
                                    msg['metadata'] = json.loads(msg['metadata'])
                                except:
                                    msg['metadata'] = {}
                            messages.append(msg)

                        return messages
                finally:
                    conn.close()

            return await asyncio.to_thread(load_sync)

        except Exception as e:
            logger.error(f"Ошибка загрузки сообщений: {e}")
            return []

    def _generate_full_report(self, session_id: str, messages: List[Dict]) -> str:
        """Генерирует полный отчет по шагам."""

        lines = []
        lines.append(f"# ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА")
        lines.append(f"")
        lines.append(f"**Session ID:** {session_id}")
        lines.append(f"**Всего сообщений:** {len(messages)}")
        lines.append(f"**Период:** {messages[0]['timestamp']} - {messages[-1]['timestamp']}")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

        # Генерируем отчет по каждому сообщению (шагу)
        for i, msg in enumerate(messages, 1):
            step_report = self._generate_step_report(i, msg)
            lines.append(step_report)
            lines.append("")

        return "\n".join(lines)

    def _generate_step_report(self, step_num: int, msg: Dict) -> str:
        """
        Генерирует отчет для одного шага по шаблону.

        Шаг User->Bot: пункты 1-3
        Шаг Bot->User: пункты 1-9
        """

        direction = msg.get('direction', 'unknown')
        is_inbound = direction == 'inbound'

        lines = []
        lines.append(f"## ===== Шаг № {step_num} =====")
        lines.append("")

        # Пункты 1-3 (для всех шагов)
        lines.append("**1. Направление:**")

        if is_inbound:
            # User -> Bot
            channel_display = self._get_channel_display(msg.get('channel', 'unknown'))
            lines.append(f"User -> Bot ({channel_display})")
        else:
            # Bot -> User
            channel_display = self._get_channel_display(msg.get('channel', 'unknown'))
            lines.append(f"Bot -> User ({channel_display})")

        lines.append("")

        lines.append(f"**2. Текст:**")
        text = msg.get('message_content', '')[:500]
        lines.append(f"{text}")
        lines.append("")

        lines.append(f"**3. txtPrb =**")

        # Извлекаем txtPrb из metadata
        metadata = msg.get('metadata', {})
        txtPrb = self._extract_txtPrb(metadata)
        if txtPrb:
            lines.append(f"{txtPrb}")
        else:
            lines.append("(нет данных)")

        lines.append("")

        # Пункты 4-9 (только для Bot -> User)
        if not is_inbound:
            lines.extend(self._generate_bot_sections(msg))

        return "\n".join(lines)

    def _generate_bot_sections(self, msg: Dict) -> List[str]:
        """Генерирует пункты 4-9 для Bot->User сообщений."""

        lines = []
        metadata = msg.get('metadata', {})

        # Пункт 4: TagSearchService
        lines.append("**4. TagSearchService**")
        tag_results = self._extract_service_results(metadata, 'tag_search')
        if tag_results:
            for result in tag_results:
                lines.append(f"{result}")
        else:
            lines.append("(не вызывался)")
        lines.append("")

        # Пункт 5: SemanticSearchService
        lines.append("**5. SemanticSearchService**")
        semantic_results = self._extract_service_results(metadata, 'semantic_search')
        if semantic_results:
            for result in semantic_results:
                lines.append(f"{result}")
        else:
            lines.append("(не вызывался)")
        lines.append("")

        # Пункт 6: VectorSearchService
        lines.append("**6. VectorSearchService**")
        vector_results = self._extract_service_results(metadata, 'vector_search')
        if vector_results:
            for result in vector_results:
                lines.append(f"{result}")
        else:
            lines.append("(не вызывался)")
        lines.append("")

        # Пункт 6.1: Итого по всем сервисам (воронка точности - UNION)
        lines.append("**6.1 Итого по всем сервисам (Воронка точности):**")
        union_results = self._extract_union_results(metadata)
        if union_results:
            for result in union_results:
                lines.append(f"{result}")
        else:
            lines.append("(нет данных)")
        lines.append("")

        # Пункт 7: Установленные фильтры
        lines.append("**7. Таблица установленных фильтров:**")
        established_filters = metadata.get('established_filters', {})
        if established_filters:
            for filter_name, filter_data in established_filters.items():
                value = filter_data.get('value', 'N/A')
                confidence = filter_data.get('confidence', 0)
                lines.append(f"{filter_name} = {value}, {confidence:.2f}")
        else:
            lines.append("(нет фильтров)")
        lines.append("")

        # Пункт 8: Прочая отладочная информация
        lines.append("**8. Прочая отладочная информация:**")
        debug_info = self._extract_debug_info(metadata)
        lines.extend(debug_info)
        lines.append("")

        # Пункт 9: Стоимость шага
        lines.append("**9. Стоимость шага:**")
        cost_info = self._extract_cost_info(msg)
        if cost_info:
            lines.extend(cost_info)
        else:
            lines.append("(нет данных о стоимости)")

        return lines

    def _extract_txtPrb(self, metadata: Dict) -> Optional[str]:
        """Извлекает txtPrb из metadata."""
        # Проверяем разные места где может быть txtPrb
        if 'txtPrb' in metadata:
            return metadata['txtPrb']

        service_detection = metadata.get('service_detection', {})
        if 'txtPrb' in service_detection:
            return service_detection['txtPrb']

        return None

    def _extract_service_results(self, metadata: Dict, service_name: str) -> List[str]:
        """Извлекает результаты работы микросервиса."""
        service_detection = metadata.get('service_detection', {})
        candidates = service_detection.get('candidates', [])

        # Фильтруем кандидатов по источнику
        service_candidates = [
            c for c in candidates
            if service_name in c.get('sources', [])
        ]

        if not service_candidates:
            return []

        results = []
        for cand in service_candidates[:5]:  # Максимум 5 кандидатов
            service_id = cand.get('service_id', 'N/A')
            name = cand.get('service_name', 'N/A')
            confidence = cand.get('confidence', 0) * 100
            results.append(f"ID:{service_id} | {name} | {confidence:.1f}%")

        return results

    def _extract_union_results(self, metadata: Dict) -> List[str]:
        """
        Извлекает UNION результаты (воронка точности).

        Показывает кандидатов после объединения всех микросервисов
        с приоритетами и sources.
        """
        service_detection = metadata.get('service_detection', {})

        # Пытаемся найти union_candidates или orchestrator_results
        union_candidates = service_detection.get('union_candidates')
        if not union_candidates:
            # Проверяем orchestrator_results
            orchestrator = service_detection.get('orchestrator_results', {})
            union_candidates = orchestrator.get('candidates')

        if not union_candidates:
            # Fallback: берем все candidates но показываем sources
            all_candidates = service_detection.get('candidates', [])
            if not all_candidates:
                return []

            # Группируем по service_id для UNION
            unique_candidates = {}
            for cand in all_candidates:
                service_id = cand.get('service_id')
                if service_id not in unique_candidates:
                    unique_candidates[service_id] = {
                        'service_id': service_id,
                        'service_name': cand.get('service_name', 'N/A'),
                        'confidence': cand.get('confidence', 0),
                        'sources': set(),
                        'priority': cand.get('priority', 0)
                    }
                # Добавляем source
                sources = cand.get('sources', [])
                unique_candidates[service_id]['sources'].update(sources)
                # Сохраняем максимальный priority
                unique_candidates[service_id]['priority'] = max(
                    unique_candidates[service_id]['priority'],
                    cand.get('priority', 0)
                )

            # Сортируем по priority
            sorted_candidates = sorted(
                unique_candidates.values(),
                key=lambda x: x['priority'],
                reverse=True
            )

            results = []
            for cand in sorted_candidates[:7]:  # Максимум 7 кандидатов
                service_id = cand['service_id']
                name = cand['service_name']
                priority = cand['priority']
                sources_str = '+'.join(sorted(cand['sources']))
                results.append(f"ID:{service_id} | {name} | priority={priority:.3f} | sources=[{sources_str}]")

            return results

        # Если есть явные union_candidates
        results = []
        for cand in union_candidates[:7]:  # Максимум 7 кандидатов
            service_id = cand.get('service_id', 'N/A')
            name = cand.get('service_name', 'N/A')
            priority = cand.get('priority', cand.get('confidence', 0))
            sources = cand.get('sources', [])
            sources_str = '+'.join(sources) if sources else 'unknown'

            if isinstance(priority, float) or isinstance(priority, int):
                results.append(f"ID:{service_id} | {name} | priority={priority:.3f} | sources=[{sources_str}]")
            else:
                results.append(f"ID:{service_id} | {name} | sources=[{sources_str}]")

        return results

    def _extract_debug_info(self, metadata: Dict) -> List[str]:
        """Извлекает отладочную информацию."""
        lines = []

        service_detection = metadata.get('service_detection', {})

        # Status
        status = service_detection.get('status', 'N/A')
        lines.append(f"- Status: {status}")

        # Message
        message = service_detection.get('message', '')
        if message and len(message) < 200:
            lines.append(f"- Message: {message}")

        # Количество кандидатов
        candidates = service_detection.get('candidates', [])
        if candidates:
            lines.append(f"- Всего кандидатов: {len(candidates)}")

        # Processing stage
        processing_stage = metadata.get('processing_stage', '')
        if processing_stage:
            lines.append(f"- Processing stage: {processing_stage}")

        # Confidence score
        confidence_score = metadata.get('confidence_score')
        if confidence_score is not None:
            lines.append(f"- Confidence score: {confidence_score:.2f}")

        return lines

    def _extract_cost_info(self, msg: Dict) -> List[str]:
        """Извлекает информацию о стоимости."""
        lines = []

        provider = msg.get('llm_provider')
        model = msg.get('llm_model')
        tokens = msg.get('tokens_used')
        cost = msg.get('cost_rub')

        if provider or model:
            model_info = f"{provider}/{model}" if provider and model else (provider or model)
            lines.append(f"- Model: {model_info}")

        if tokens:
            lines.append(f"- Tokens: {tokens}")

        if cost is not None:
            lines.append(f"- Cost: {cost:.4f} руб")

        return lines

    def _get_channel_display(self, channel: str) -> str:
        """Возвращает человекочитаемое название канала."""
        channel_map = {
            'telegram': 'Telegram',
            'web': 'Web-чат',
            'whatsapp': 'WhatsApp',
            'maxchat': 'Мессенджер Макс',
            'test_bot': 'Программный тест',
            'transcriber': 'Голосовой транскрибатор'
        }
        return channel_map.get(channel, channel)


# Функция для быстрого вызова
async def generate_trace_v3(session_id: str) -> str:
    """
    Быстрая генерация отчета трассировки v3.0

    Args:
        session_id: ID сессии

    Returns:
        str: Текст отчета
    """
    service = TraceReportServiceV3()
    return await service.generate_trace_report(session_id)
