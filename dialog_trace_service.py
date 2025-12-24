#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Микросервис трассировки (追踪服务 - zhuīzōng fúwù) диалогов для диагностики

Назначение:
- Выдача детальной трассировки диалога по воронке точности
- Анализ ответов всех микросервисов на каждом этапе
- Контроль промтов LLM и установленных фильтров
- Проверка памяти (context) диалога

Использование:
    python dialog_trace_service.py --session-id web_123_abc
    python dialog_trace_service.py --dialog-id dialog_123_20251224_080000
    python dialog_trace_service.py --telegram-user-id 123456789
"""

import logging
import asyncio
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DialogTraceService:
    """
    Микросервис трассировки диалогов (对话追踪服务 - duìhuà zhuīzōng fúwù)

    Анализирует прохождение диалога через воронку точности:
    1. Ответы микросервисов (TagSearch, SemanticSearch, VectorSearch, AIAgent)
    2. Промты LLM (главный AI агент, анализ фильтров)
    3. Установленные фильтры (location, category, incident)
    4. Память диалога (контекст, история)
    """

    def __init__(self):
        """Инициализация микросервиса трассировки"""
        self.main_agent = None
        self.message_handler = None
        self._initialize_services()

    def _initialize_services(self):
        """Инициализация сервисов"""
        try:
            from main_agent import MainAgent
            from message_handler_service import MessageHandlerService

            self.main_agent = MainAgent()
            self.message_handler = MessageHandlerService(main_agent=self.main_agent)

            logger.info("DialogTraceService: сервисы инициализированы")
        except Exception as e:
            logger.error(f"Ошибка инициализации сервисов: {e}")
            raise

    async def trace_dialog_by_session(self, session_id: str, limit: int = 50) -> Dict[str, Any]:
        """
        Трассировка диалога по session_id

        Args:
            session_id: ID сессии
            limit: Лимит сообщений для анализа

        Returns:
            Словарь с детальной трассировкой диалога
        """
        logger.info(f"Начинаю трассировку сессии: {session_id}")

        # Получаем историю сообщений
        messages = await self.message_handler.get_session_messages(session_id, limit)

        if not messages:
            return {
                "status": "error",
                "message": f"Сообщения не найдены для session_id={session_id}"
            }

        # Анализируем каждое сообщение
        trace_result = {
            "status": "success",
            "session_id": session_id,
            "total_messages": len(messages),
            "messages_trace": [],
            "summary": self._generate_summary(messages)
        }

        for i, msg in enumerate(messages, 1):
            message_trace = await self._trace_single_message(msg, i)
            trace_result["messages_trace"].append(message_trace)

        return trace_result

    async def trace_dialog_by_telegram_user(self, telegram_user_id: int, limit: int = 50) -> Dict[str, Any]:
        """
        Трассировка диалога по telegram_user_id

        Args:
            telegram_user_id: ID пользователя Telegram
            limit: Лимит сообщений для анализа

        Returns:
            Словарь с детальной трассировкой диалога
        """
        logger.info(f"Начинаю трассировку пользователя Telegram: {telegram_user_id}")

        # Получаем сессии пользователя
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT session_id
                FROM dialog_messages
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                [f"tg_{telegram_user_id}", limit]
            )
            sessions = [row[0] for row in cursor.fetchall()]

        if not sessions:
            return {
                "status": "error",
                "message": f"Сессии не найдены для telegram_user_id={telegram_user_id}"
            }

        # Используем последнюю сессию
        latest_session = sessions[0] if sessions else None
        if latest_session:
            return await self.trace_dialog_by_session(latest_session, limit)

        return {
            "status": "error",
            "message": "Нет активных сессий"
        }

    async def _trace_single_message(self, message: Dict[str, Any], index: int) -> Dict[str, Any]:
        """
        Трассировка отдельного сообщения

        Args:
            message: Данные сообщения из БД
            index: Порядковый номер сообщения

        Returns:
            Детальная трассировка сообщения
        """
        metadata = message.get("metadata", {})
        # metadata уже dict (jsonb из PostgreSQL), не нужно json.loads
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        trace = {
            "index": index,
            "message_id": message.get("id"),
            "direction": message.get("direction"),  # inbound/outbound
            "text": message.get("text"),
            "timestamp": message.get("timestamp"),
            "metadata": metadata,
            "microservices_results": {},
            "llm_prompts": {},
            "filters_applied": {},
            "dialog_memory": {}
        }

        # Если это входящее сообщение - анализируем обработку
        if message.get("direction") == "inbound":
            # Симулируем обработку через MainAgent
            microservices_trace = await self._trace_microservices(message.get("text"))
            trace["microservices_results"] = microservices_trace

        # Извлекаем данные из metadata
        metadata = trace["metadata"]
        trace["filters_applied"] = metadata.get("filters", {})
        trace["dialog_memory"] = metadata.get("memory", {})

        # Если были LLM вызовы - извлекаем промты
        if "llm_calls" in metadata:
            trace["llm_prompts"] = metadata["llm_calls"]

        return trace

    async def _trace_microservices(self, message_text: str) -> Dict[str, Any]:
        """
        Трассировка ответов микросервисов

        Args:
            message_text: Текст сообщения

        Returns:
            Результаты работы всех микросервисов
        """
        results = {
            "tag_search": None,
            "semantic_search": None,
            "vector_search": None,
            "ai_agent": None,
            "intersection": None,
            "final_candidates": []
        }

        try:
            # Запускаем микросервисы параллельно
            search_tasks = []
            if self.main_agent.tag_search:
                search_tasks.append(self._run_tag_search_trace(message_text))
            if self.main_agent.semantic_search:
                search_tasks.append(self._run_semantic_search_trace(message_text))
            if self.main_agent.vector_search:
                search_tasks.append(self._run_vector_search_trace(message_text))

            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Собираем результаты
            for i, result in enumerate(search_results):
                if not isinstance(result, Exception) and result.get("status") == "success":
                    method = result.get("method")
                    if method == "tag_search":
                        results["tag_search"] = result
                    elif method == "semantic_search":
                        results["semantic_search"] = result
                    elif method == "vector_search":
                        results["vector_search"] = result

                    # Собираем交集 (jiāojí - пересечение) всех услуг
                    results["final_candidates"].extend(result.get("candidates", []))

        except Exception as e:
            logger.error(f"Ошибка при трассировке микросервисов: {e}")
            results["error"] = str(e)

        return results

    async def _run_tag_search_trace(self, message_text: str) -> Dict[str, Any]:
        """Трассировка TagSearchService"""
        try:
            result = await self.main_agent._run_tag_search(message_text)
            return result
        except Exception as e:
            return {"status": "error", "method": "tag_search", "error": str(e)}

    async def _run_semantic_search_trace(self, message_text: str) -> Dict[str, Any]:
        """Трассировка SemanticSearchService"""
        try:
            result = await self.main_agent._run_semantic_search(message_text)
            return result
        except Exception as e:
            return {"status": "error", "method": "semantic_search", "error": str(e)}

    async def _run_vector_search_trace(self, message_text: str) -> Dict[str, Any]:
        """Трассировка VectorSearchService"""
        try:
            result = await self.main_agent._run_vector_search(message_text)
            return result
        except Exception as e:
            return {"status": "error", "method": "vector_search", "error": str(e)}

    def _generate_summary(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Генерация саммари (总结 - zǒngjié) диалога

        Args:
            messages: Список сообщений

        Returns:
            Саммари диалога
        """
        inbound_count = sum(1 for m in messages if m.get("direction") == "inbound")
        outbound_count = sum(1 for m in messages if m.get("direction") == "outbound")

        return {
            "total_messages": len(messages),
            "inbound_messages": inbound_count,
            "outbound_messages": outbound_count,
            "first_message_time": messages[0].get("timestamp") if messages else None,
            "last_message_time": messages[-1].get("timestamp") if messages else None,
        }

    def format_trace_report(self, trace_data: Dict[str, Any]) -> str:
        """
        Форматирование отчета трассировки для вывода

        Args:
            trace_data: Данные трассировки

        Returns:
            Отформатированный отчет в виде строки
        """
        if trace_data.get("status") == "error":
            return f"ОШИБКА: {trace_data.get('message')}"

        report = []
        report.append("=" * 80)
        report.append("ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА")
        report.append("=" * 80)
        report.append(f"Session ID: {trace_data.get('session_id')}")
        report.append(f"Всего сообщений: {trace_data.get('total_messages')}")
        report.append("")

        for msg_trace in trace_data.get("messages_trace", []):
            report.append("-" * 80)
            report.append(f"Сообщение #{msg_trace.get('index')}")
            report.append(f"Направление: {msg_trace.get('direction')}")
            report.append(f"Текст: {msg_trace.get('text')}")
            report.append(f"Время: {msg_trace.get('timestamp')}")

            # Результаты микросервисов
            microservices = msg_trace.get("microservices_results", {})
            if microservices:
                report.append("\nРезультаты микросервисов:")
                for service_name, result in microservices.items():
                    if service_name != "final_candidates" and result:
                        report.append(f"  {service_name}:")
                        if isinstance(result, dict):
                            candidates = result.get("candidates", [])
                            report.append(f"    Найдено услуг: {len(candidates)}")
                            for cand in candidates[:3]:  # Первые 3 кандидата
                                report.append(f"      - ID:{cand.get('service_id')} | {cand.get('service_name')} | {cand.get('confidence'):.2%}")

            # Фильтры
            filters = msg_trace.get("filters_applied", {})
            if filters:
                report.append("\nУстановленные фильтры:")
                for filter_name, filter_value in filters.items():
                    report.append(f"  {filter_name}: {filter_value}")

            report.append("")

        return "\n".join(report)


async def main():
    """Главная функция для CLI"""
    import argparse

    parser = argparse.ArgumentParser(description="Микросервис трассировки диалогов")
    parser.add_argument("--session-id", help="ID сессии для трассировки")
    parser.add_argument("--dialog-id", help="ID диалога для трассировки")
    parser.add_argument("--telegram-user-id", type=int, help="ID пользователя Telegram")
    parser.add_argument("--limit", type=int, default=50, help="Лимит сообщений")
    parser.add_argument("--output", choices=["console", "json"], default="console", help="Формат вывода")

    args = parser.parse_args()

    # Инициализация Django
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
    django.setup()

    # Создаем сервис трассировки
    trace_service = DialogTraceService()

    # Выполняем трассировку
    trace_result = None

    if args.session_id:
        trace_result = await trace_service.trace_dialog_by_session(args.session_id, args.limit)
    elif args.dialog_id:
        # dialog_id == session_id для нашей системы
        trace_result = await trace_service.trace_dialog_by_session(args.dialog_id, args.limit)
    elif args.telegram_user_id:
        trace_result = await trace_service.trace_dialog_by_telegram_user(args.telegram_user_id, args.limit)
    else:
        parser.print_help()
        return

    # Вывод результатов
    if args.output == "json":
        print(json.dumps(trace_result, indent=2, ensure_ascii=False, default=str))
    else:
        report = trace_service.format_trace_report(trace_result)
        print(report)


if __name__ == "__main__":
    asyncio.run(main())
