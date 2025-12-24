#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MessageHandlerService - единый микросервис обработки сообщений из всех каналов

Принимает сообщения из:
- Telegram
- WhatsApp
- Мессенджер Макс
- Веб-сайт (Django)
- Тестовый бот-имитатор
- Голосовой транскрибатор

Логирует все сообщения в БД и передает в MainAgent для обработки
"""

import logging
import uuid
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class MessageHandlerService:
    """Единый сервис обработки сообщений из всех каналов"""

    def __init__(self, main_agent=None):
        """
        Инициализация сервиса

        Args:
            main_agent: Экземпляр MainAgent для обработки сообщений
        """
        self.main_agent = main_agent

        # Инициализируем MessageCleanerService
        try:
            from message_cleaner_service import MessageCleanerService
            # Передаем ai_agent из MainAgent для LLM-очистки
            ai_agent = main_agent.ai_agent if main_agent else None
            self.message_cleaner = MessageCleanerService(ai_agent_service=ai_agent)
            logger.info("MessageCleanerService инициализирован в MessageHandlerService")
        except ImportError:
            self.message_cleaner = None
            logger.warning("MessageCleanerService не найден, очистка сообщений отключена")

        logger.info("MessageHandlerService инициализирован")

    async def handle_incoming_message(
        self,
        text: str,
        user_id: str,
        channel: str = 'telegram',
        message_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        django_user_id: Optional[int] = None
    ) -> Dict:
        """
        Обработка входящего сообщения из любого канала

        Args:
            text: Текст сообщения
            user_id: ID пользователя в канале
            channel: Канал связи (telegram, whatsapp, web, test_bot, transcriber)
            message_id: ID сообщения в канале
            session_id: ID сессии диалога (если None, создается новый)
            metadata: Дополнительные метаданные от канала
            django_user_id: ID пользователя Django (если есть)

        Returns:
            Dict: Результат обработки с ответом бота
                {
                    'status': 'success' | 'error',
                    'response': str,  # Ответ бота
                    'message_log_id': int,  # ID записанного сообщения
                    'session_id': str,  # ID сессии
                    'service_detected': Optional[dict]  # Если услуга определена
                }
        """
        try:
            # Генерируем уникальные ID если не переданы
            if not message_id:
                message_id = f"{channel}_{uuid.uuid4().hex[:16]}"
            if not session_id:
                session_id = f"{channel}_{user_id}"

            logger.info(
                f"MessageHandler: Входящее сообщение из {channel} | "
                f"User: {user_id} | Session: {session_id} | Text: '{text[:50]}...'"
            )

            # 1. Логируем входящее сообщение в БД
            message_log = await self._log_message(
                text=text,
                user_id=user_id,
                channel=channel,
                message_id=message_id,
                session_id=session_id,
                direction='inbound',
                metadata=metadata or {},
                django_user_id=django_user_id
            )

            # 2. Получаем историю диалога для контекста
            dialog_history = await self._get_dialog_history(session_id, limit=10)

            # 2.5. Очищаем сообщение от мусора (приветы, insignificant words)
            search_text = text
            if self.message_cleaner:
                cleaned_text, clean_metadata = self.message_cleaner.clean_message(text)
                search_text = cleaned_text

                # Проверяем: если сообщение только приветствие - отвечаем приветствием
                if self.message_cleaner.is_greeting_only(text):
                    logger.info(f"Обнаружено чистое приветствие от user {user_id}")
                    await self._log_message(
                        text="Здравствуйте! Опишите вашу проблему, и я попробую помочь.",
                        user_id=user_id,
                        channel=channel,
                        message_id=f"bot_{uuid.uuid4().hex[:16]}",
                        session_id=session_id,
                        direction='outbound',
                        metadata={'auto_greeting': True}
                    )
                    return {
                        'status': 'success',
                        'response': "Здравствуйте! Опишите вашу проблему, и я попробую помочь.",
                        'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None,
                        'session_id': session_id,
                        'is_greeting': True
                    }

                if clean_metadata.get('removed_greeting') or clean_metadata.get('removed_fillers'):
                    logger.info(f"Сообщение очищено: удалено {clean_metadata}")

            # 3. Передаем в MainAgent для обработки
            if not self.main_agent:
                logger.warning("MessageHandler: MainAgent не инициализирован")
                return {
                    'status': 'error',
                    'error': 'MainAgent not available',
                    'session_id': session_id,
                    'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None
                }

            # Вызываем MainAgent
            # Устанавливаем is_followup=True если есть история диалога (более 2 сообщений)
            is_followup = len(dialog_history) > 2

            result = await self.main_agent.process_service_detection(
                message_text=search_text,  # ИСПРАВЛЕНО: используем очищенный текст
                user_context={
                    'original_message': text,  # Сохраняем оригинал для контекста
                    'user_id': user_id,
                    'channel': channel,
                    'session_id': session_id,
                    'dialog_history': dialog_history,  # История через user_context
                    'is_followup': is_followup,  # Флаг для объединения контекста
                    'cleaned_message': search_text  # Добавляем очищенное сообщение
                }
            )

            # 4. Формируем ответ бота
            bot_response = self._extract_bot_response(result)

            # 5. Логируем исходящее сообщение (ответ бота)
            if bot_response:
                await self._log_message(
                    text=bot_response,
                    user_id=user_id,
                    channel=channel,
                    message_id=f"bot_{uuid.uuid4().hex[:16]}",
                    session_id=session_id,
                    direction='outbound',
                    metadata={'service_result': result}
                )

            logger.info(
                f"MessageHandler: Обработка завершена | "
                f"Session: {session_id} | Status: {result.get('status')} | "
                f"Response: '{bot_response[:50] if bot_response else 'NO'}...'"
            )

            return {
                'status': 'success',
                'response': bot_response,
                'raw_result': result,
                'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None,
                'session_id': session_id,
                'service_detected': result.get('service_id') if result.get('status') == 'SUCCESS' else None
            }

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка обработки сообщения: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'session_id': session_id if session_id else f"{channel}_{user_id}"
            }

    async def _log_message(
        self,
        text: str,
        user_id: str,
        channel: str,
        message_id: str,
        session_id: str,
        direction: str,
        metadata: Dict = None,
        django_user_id: Optional[int] = None
    ) -> Dict:
        """
        Логирование сообщения в БД

        Returns:
            Dict: Созданная запись сообщения
        """
        try:
            from message_handler.models import MessageLog
            from django.contrib.auth import get_user_model

            def log_sync():
                # Находим пользователя Django если передан ID
                django_user = None
                if django_user_id:
                    User = get_user_model()
                    try:
                        django_user = User.objects.get(id=django_user_id)
                    except User.DoesNotExist:
                        pass

                # Создаем запись
                log_entry = MessageLog.objects.create(
                    channel=channel,
                    direction=direction,
                    message_id=message_id,
                    user_id=user_id,
                    session_id=session_id,
                    text=text,
                    metadata=metadata or {},
                    django_user=django_user
                )
                return {
                    'id': log_entry.id,
                    'created_at': log_entry.created_at.isoformat()
                }

            return await sync_to_async(log_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка логирования: {e}")
            return {}

    async def _get_dialog_history(self, session_id: str, limit: int = 10) -> list:
        """
        Получить историю диалога из БД

        Args:
            session_id: ID сессии
            limit: Максимальное количество сообщений

        Returns:
            list: История в формате для MainAgent
                [
                    {'role': 'user', 'text': '...', 'timestamp': '...'},
                    {'role': 'bot', 'text': '...', 'timestamp': '...'}
                ]
        """
        try:
            from message_handler.models import MessageLog

            def get_history_sync():
                messages = MessageLog.objects.filter(
                    session_id=session_id
                ).order_by('-created_at')[:limit]

                return [
                    {
                        'role': 'user' if msg.direction == 'inbound' else 'bot',
                        'text': msg.text,
                        'timestamp': msg.created_at.isoformat()
                    }
                    for msg in reversed(messages)
                ]

            return await sync_to_async(get_history_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка получения истории: {e}")
            return []

    def _extract_bot_response(self, result: Dict) -> str:
        """
        Извлечь текст ответа бота из результата MainAgent

        Args:
            result: Результат от MainAgent

        Returns:
            str: Текст ответа для отправки пользователю
        """
        if not result:
            return "Произошла ошибка обработки"

        status = result.get('status')

        if status == 'SUCCESS':
            # Услуга определена однозначно
            service_name = result.get('service_name', 'услуга')
            message = result.get('message')

            if message:
                return message
            return f"Понял, у вас: {service_name}. Это правильно?"

        elif status == 'AMBIGUOUS':
            # Нужен уточняющий вопрос
            message = result.get('message')
            if message:
                return message

            # Если нет message, используем список кандидатов
            candidates = result.get('candidates', [])
            if candidates:
                names = [c.get('service_name') for c in candidates[:3]]
                return f"Уточните, пожалуйста: это {', '.join(names)}?"

            return "Пожалуйста, уточните детали проблемы."

        elif status == 'ERROR':
            error = result.get('error', 'Неизвестная ошибка')
            return f"Произошла ошибка: {error}"

        else:
            # Fallback
            return "Понял your message. Опишите подробнее что случилось."

    async def get_session_messages(self, session_id: str, limit: int = 50) -> list:
        """
        Получить все сообщения сессии (для админки/отладки)

        Args:
            session_id: ID сессии
            limit: Максимальное количество сообщений

        Returns:
            list: Сообщения с метаданными
        """
        try:
            from message_handler.models import MessageLog

            def get_messages_sync():
                messages = MessageLog.objects.filter(
                    session_id=session_id
                ).order_by('created_at')[:limit]

                return [
                    {
                        'id': msg.id,
                        'channel': msg.get_channel_display(),
                        'direction': msg.get_direction_display(),
                        'text': msg.text,
                        'timestamp': msg.created_at.isoformat(),
                        'metadata': msg.metadata
                    }
                    for msg in messages
                ]

            return await sync_to_async(get_messages_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка получения сообщений сессии: {e}")
            return []
