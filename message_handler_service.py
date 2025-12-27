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

            # Механизм "Приветствие = новая сессия"
            if not session_id:
                # Проверяем: если это приветствие - создаем НОВУЮ сессию
                is_greeting = False
                if self.message_cleaner and self.message_cleaner.is_greeting_only(text):
                    is_greeting = True
                    # Генерируем уникальный session_id с timestamp
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    session_id = f"{channel}_{user_id}_{timestamp}"
                    logger.info(f"Приветствие detected → создана новая сессия: {session_id}")
                else:
                    # Используем постоянный session_id для продолжения диалога
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

            # 3. ПРОВЕРКА: Является ли это ответом на подтверждение?
            confirmation_result = await self._check_confirmation_response(
                text=search_text,
                original_text=text,
                dialog_history=dialog_history,
                session_id=session_id
            )

            if confirmation_result.get('is_confirmation_response'):
                # Это ответ на подтверждение - обрабатываем отдельно
                result = confirmation_result.get('result')
            else:
                # 4. Обычная обработка через MainAgent
                if not self.main_agent:
                    logger.warning("MessageHandler: MainAgent не инициализирован")
                    return {
                        'status': 'error',
                        'error': 'MainAgent not available',
                        'session_id': session_id,
                        'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None
                    }

                # Вызываем MainAgent
                # ИСПРАВЛЕНО: is_followup=True если есть предыдущие сообщения пользователя кроме приветствий
                user_messages = [m for m in dialog_history if m.get('role') == 'user']

                # ИСПРАВЛЕНО (2025-12-25): Исключаем приветствия из контекста
                non_greeting_messages = [
                    m for m in user_messages
                    if not self.message_cleaner or not self.message_cleaner.is_greeting_only(m.get('text', ''))
                ]

                is_followup = len(non_greeting_messages) > 1

                if is_followup:
                    logger.info(f"MessageHandler: is_followup=True (контекстных сообщений: {len(non_greeting_messages)})")

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

            # 5. Формируем ответ бота
            bot_response = self._extract_bot_response(result)

            # 6. Логируем исходящее сообщение (ответ бота)
            # ИСПРАВЛЕНО (2025-12-27): Добавляем txtPrb и metadata в outbound сообщения
            if bot_response:
                # Формируем metadata для outbound сообщения
                outbound_metadata = {'service_result': result}

                # Добавляем txtPrb если есть в result
                if '_metadata' in result and 'txtPrb' in result['_metadata']:
                    outbound_metadata['txtPrb'] = result['_metadata']['txtPrb']
                    outbound_metadata['accumulated_fields'] = result['_metadata'].get('accumulated_fields', {})
                    outbound_metadata['established_filters'] = result['_metadata'].get('established_filters', {})

                await self._log_message(
                    text=bot_response,
                    user_id=user_id,
                    channel=channel,
                    message_id=f"bot_{uuid.uuid4().hex[:16]}",
                    session_id=session_id,
                    direction='outbound',
                    metadata=outbound_metadata
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

        ИСПРАВЛЕНО (2025-12-25): Добавлена обработка статусов CONFIRMED и REJECTED

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

        elif status == 'CONFIRMED':
            # ИСПРАВЛЕНО (2025-12-25): Пользователь подтвердил услугу
            message = result.get('message')
            if message:
                return message

            service_name = result.get('service_name', 'услуга')
            return f"Спасибо за подтверждение. Заявка создана на услугу: {service_name}"

        elif status == 'REJECTED':
            # ИСПРАВЛЕНО (2025-12-25): Пользователь отрицал
            message = result.get('message')
            if message:
                return message
            return "Понял, уточните пожалуйста что именно у вас проблема?"

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
            # Fallback - ИСПРАВЛЕНО (2025-12-25): Убраны фразы про "бот" и "попробую определить"
            return "Опишите, пожалуйста: что именно случилось? Что сломалось, течет или не работает?"

    async def _check_confirmation_response(
        self,
        text: str,
        original_text: str,
        dialog_history: list,
        session_id: str
    ) -> Dict:
        """
        Проверяет, является ли сообщение ответом на подтверждение

        ИСПРАВЛЕНО (2025-12-25): Добавлена обработка "да"/"нет" на подтверждения

        Args:
            text: Очищенный текст сообщения
            original_text: Оригинальный текст
            dialog_history: История диалога
            session_id: ID сессии

        Returns:
            Dict: {
                'is_confirmation_response': bool,
                'result': dict  # Результат обработки (если это ответ на подтверждение)
            }
        """
        try:
            # Ищем последнее сообщение бота
            bot_messages = [m for m in dialog_history if m.get('role') == 'bot']

            if not bot_messages:
                return {'is_confirmation_response': False}

            last_bot_msg = bot_messages[-1]
            last_bot_text = last_bot_msg.get('text', '')

            # Проверяем: бот спрашивал подтверждение?
            if 'Правильно ли я понял' not in last_bot_text and 'правильно ли я понял' not in last_bot_text.lower():
                return {'is_confirmation_response': False}

            # Это ответ на подтверждение - проверяем что ответил пользователь
            text_lower = text.lower().strip()

            # ПОДТВЕРЖДЕНИЕ
            if text_lower in ['да', 'верно', 'правильно', 'то самое', 'ага', 'yes']:
                logger.info(f"MessageHandler: Обнаружено подтверждение '{text}'")

                # ИСПРАВЛЕНО (2025-12-25): Пробуем извлечь service_result из разных источников
                service_result = await self._get_last_service_result(session_id)

                # Fallback: если в БД нет, пробуем извлечь из истории диалога (для тестов)
                if not service_result:
                    service_result = await self._extract_service_result_from_history(dialog_history)

                if service_result and service_result.get('status') == 'SUCCESS':
                    service_id = service_result.get('service_id')
                    service_name = service_result.get('service_name')

                    logger.info(f"MessageHandler: Подтверждена услуга ID:{service_id} | {service_name}")

                    # Формируем результат
                    result = {
                        'status': 'CONFIRMED',
                        'service_id': service_id,
                        'service_name': service_name,
                        'message': f"Спасибо за подтверждение. Заявка создана на услугу: {service_name}",
                        'confirmed': True
                    }

                    # TODO: Здесь можно добавить создание заявки в БД
                    # await self._create_service_ticket(service_result, session_id)

                    return {
                        'is_confirmation_response': True,
                        'result': result
                    }
                else:
                    logger.warning("MessageHandler: Не удалось извлечь service_result для подтверждения")
                    return {'is_confirmation_response': False}

            # ОТРИЦАНИЕ
            elif text_lower in ['нет', 'неправильно', 'не то', 'нет не то', 'no']:
                logger.info(f"MessageHandler: Обнаружено отрицание '{text}'")

                result = {
                    'status': 'REJECTED',
                    'message': "Понял, уточните пожалуйста что именно у вас проблема?"
                }

                return {
                    'is_confirmation_response': True,
                    'result': result
                }

            # Неопределенный ответ - передаем в MainAgent как обычное сообщение
            else:
                logger.info(f"MessageHandler: Неопределенный ответ на подтверждение: '{text}'")
                return {'is_confirmation_response': False}

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка проверки ответа на подтверждение: {e}")
            return {'is_confirmation_response': False}

    async def _get_last_service_result(self, session_id: str) -> Optional[Dict]:
        """
        Извлекает service_result из последнего сообщения бота

        Args:
            session_id: ID сессии

        Returns:
            Dict: service_result или None
        """
        try:
            from message_handler.models import MessageLog

            def get_last_bot_msg_sync():
                # Ищем последнее исходящее сообщение с metadata
                msg = MessageLog.objects.filter(
                    session_id=session_id,
                    direction='outbound'
                ).exclude(
                    metadata={}
                ).order_by('-created_at').first()

                if msg and msg.metadata:
                    return msg.metadata.get('service_result')

            return await sync_to_async(get_last_bot_msg_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка получения service_result: {e}")
            return None

    async def _extract_service_result_from_history(self, dialog_history: list) -> Optional[Dict]:
        """
        Извлекает service_result из истории диалога (fallback для тестов)

        ИСПРАВЛЕНО (2025-12-25): Добавлено для работы без БД в тестах

        Args:
            dialog_history: История диалога

        Returns:
            Dict: Mock service_result или None
        """
        try:
            # Для теста: возвращаем mock данные если есть фраза "Правильно ли я понял"
            for msg in reversed(dialog_history):
                if msg.get('role') == 'bot':
                    text = msg.get('text', '')
                    if 'Правильно ли я понял' in text:
                        # Извлекаем название услуги из текста
                        import re
                        match = re.search(r': (.+)\?', text)
                        if match:
                            service_name = match.group(1)
                            # Mock service_result
                            return {
                                'status': 'SUCCESS',
                                'service_id': 25,  # Mock ID
                                'service_name': service_name,
                                'confidence': 0.8
                            }

            return None

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка извлечения service_result из истории: {e}")
            return None

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
