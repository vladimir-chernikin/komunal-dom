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
            session_id: ID сессии диалога (если None, создается/продлевается автоматически)
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
            # ИСПРАВЛЕНО (2026-03-04): Инициализируем PerformanceTracer для трекинга времени
            from performance_tracer import PerformanceTracer
            tracer = PerformanceTracer(session_id=session_id)
            tracer.start("total_request")

            # Генерируем уникальные ID если не переданы
            if not message_id:
                message_id = f"{channel}_{uuid.uuid4().hex[:16]}"

            # ИСПРАВЛЕНО (2025-12-28): Умное управление сессиями
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
                    # ИСПРАВЛЕНО: Ищем активную сессию (не старше 1 часа)
                    session_id = await self._find_or_create_active_session(user_id, channel)

            logger.info(
                f"MessageHandler: Входящее сообщение из {channel} | "
                f"User: {user_id} | Session: {session_id} | Text: '{text[:50]}...'"
            )

            # ИСПРАВЛЕНО (2026-03-05): Логируем входящий metadata для отладки
            if metadata:
                logger.info(f"[DEBUG] Входящий metadata: {list(metadata.keys())}, api_info={metadata.get('api_info')}")
            else:
                logger.warning(f"[DEBUG] Входящий metadata ПОУСТО!")

            # 1. Логируем входящее сообщение в БD
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

            # ИСПРАВЛЕНО (2026-03-05): Явно сохраняем api_info и client_system в metadata сразу после логирования
            # Это гарантирует что эти поля не потеряются при последующих обновлениях через MainAgent
            inbound_message_id = message_log.get('id') if isinstance(message_log, dict) else None
            if metadata and isinstance(metadata, dict) and inbound_message_id:
                preserved_fields = {}
                if 'api_info' in metadata:
                    preserved_fields['api_info'] = metadata['api_info']
                if 'client_system' in metadata:
                    preserved_fields['client_system'] = metadata['client_system']

                if preserved_fields:
                    logger.info(f"[DEBUG] Сохраняем api_info/client_system в metadata id={inbound_message_id}: {list(preserved_fields.keys())}")
                    await self._update_message_metadata(inbound_message_id, preserved_fields)

            # 2. Получаем историю диалога для контекста
            dialog_history = await self._get_dialog_history(session_id, limit=10)

            # 2.5. Очищаем сообщение от мусора (приветы, insignificant words)
            search_text = text
            if self.message_cleaner:
                cleaned_text, clean_metadata = await self.message_cleaner.clean_message(text)
                search_text = cleaned_text

                # Проверяем: если сообщение только приветствие - отвечаем приветствием
                # ИСПРАВЛЕНО (2026-01-06): НЕ логируем здесь - будет залогировано ниже (строки 247-255)
                if self.message_cleaner.is_greeting_only(text):
                    logger.info(f"Обнаружено чистое приветствие от user {user_id}")

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

                # ИСПРАВЛЕНО (2025-12-28): Изменена логика is_followup
                # Старая: > 1 (только на 3+ сообщении)
                # Новая: >= 1 (уже на 2-м сообщении, первом после приветствия)
                is_followup = len(non_greeting_messages) >= 1

                if is_followup:
                    logger.info(f"MessageHandler: is_followup=True (контекстных сообщений: {len(non_greeting_messages)})")

                # ИСПРАВЛЕНО (2026-01-10): Извлекаем established_filters из последнего bot сообщения
                # КРИТИЧЕСКИ ВАЖНО: established_filters должны передаваться между вызовами MainAgent!
                established_filters = None
                # ИСПРАВЛЕНО (2026-02-16): Извлекаем accumulated_fields из последнего bot сообщения
                # ИСПРАВЛЕНО (2026-02-04): Извлекаем txtStopQ (запрещенные вопросы) из последнего bot сообщения
                # КРИТИЧЕСКИ ВАЖНО: txtStopQ накапливает глупые вопросы чтобы не повторять их!
                txt_stop_questions = []  # Список запрещенных вопросов
                if dialog_history and len(dialog_history) > 0:
                    # Ищем последнее сообщение бота
                    for msg in reversed(dialog_history):
                        if msg.get('role') == 'bot':
                            metadata = msg.get('metadata', {})
                            if isinstance(metadata, dict):
                                # Извлекаем established_filters
                                if 'established_filters' in metadata:
                                    established_filters = metadata['established_filters']
                                    logger.info(f"[DEBUG] Извлечены established_filters из истории: {list(established_filters.keys()) if established_filters else 'None'}")
                                # ИСПРАВЛЕНО (2026-02-24): accumulated_fields УДАЛЁН - используем только txtPrb
                                # Извлекаем txtStopQ (запрещенные вопросы)
                                if 'txtStopQ' in metadata:
                                    txt_stop_questions = metadata['txtStopQ']
                                    logger.info(f"[DEBUG] Извлечены txtStopQ из истории: {len(txt_stop_questions)} вопросов")
                                    break

                # ИСПРАВЛЕНО (2026-01-05): Отладочный лог - проверяем dialog_history ПЕРЕД передачей в MainAgent
                logger.info(f"[DEBUG] dialog_history ПЕРЕД передачей в MainAgent: {len(dialog_history)} сообщений")
                if dialog_history and len(dialog_history) > 0:
                    for i, msg in enumerate(dialog_history[-3:], 1):
                        logger.info(f"  {i}. [{msg.get('role')}] {msg.get('text', '')[:50]}")

                result = await self.main_agent.process_service_detection(
                    message_text=search_text,  # ИСПРАВЛЕНО: используем очищенный текст
                    user_context={
                        'original_message': text,  # Сохраняем оригинал для контекста
                        'user_id': user_id,
                        'channel': channel,
                        'session_id': session_id,
                        'message_id': message_log.get('id') if isinstance(message_log, dict) else None,  # ИСПРАВЛЕНО (2026-01-06)
                        'dialog_history': dialog_history,  # История через user_context
                        'is_followup': is_followup,  # Флаг для объединения контекста
                        'cleaned_message': search_text,  # Добавляем очищенное сообщение
                        'established_filters': established_filters,  # ИСПРАВЛЕНО (2026-01-10): ПЕРЕДАЕМ ФИЛЬТРЫ!
                        # ИСПРАВЛЕНО (2026-02-24): accumulated_fields УДАЛЁН
                        'txtStopQ': txt_stop_questions,  # ИСПРАВЛЕНО (2026-02-04): ПЕРЕДАЕМ ЗАПРЕЩЕННЫЕ ВОПРОСЫ!
                        # ИСПРАВЛЕНО (2026-03-04): PerformanceTracer для замера времени
                        'performance_tracer': tracer
                    }
                )

            # ИСПРАВЛЕНО (2026-01-06): Обновляем metadata для inbound сообщения с txtPrb
            # КРИТИЧЕСКИ ВАЖНО: TraceReportService читает metadata из БД!
            logger.info(f"[METADATA CHECK] _metadata в result: {('_metadata' in result)}, message_log is dict: {isinstance(message_log, dict)}")
            if '_metadata' in result and isinstance(message_log, dict):
                inbound_message_id = message_log.get('id')
                logger.info(f"[METADATA CHECK] inbound_message_id={inbound_message_id}, condition: {inbound_message_id and inbound_message_id > 0}")
                if inbound_message_id and inbound_message_id > 0:
                    try:
                        # ИСПРАВЛЕНО (2026-02-17): КРИТИЧЕСКИЙ ЛОГ (БЕЗОПАСНЫЙ)
                        metadata_obj = result.get('_metadata', {})
                        txtPrb_val = metadata_obj.get('txtPrb', '(нет)') if isinstance(metadata_obj, dict) else '(нет)'
                        logger.info(f"[CRITICAL] Обновляем metadata для inbound id={inbound_message_id}, txtPrb='{str(txtPrb_val)[:60]}...'")
                        await self._update_message_metadata(
                            message_id=inbound_message_id,
                            metadata=result['_metadata']
                        )
                        logger.info(f"[DEBUG] ✅ Metadata обновлена для inbound сообщения id={inbound_message_id}")
                    except Exception as e:
                        logger.warning(f"[WARNING] Не удалось обновить metadata для inbound: {e}")
                        logger.error(f"[ERROR] Traceback:", exc_info=True)
                else:
                    logger.warning(f"[WARNING] inbound_message_id={inbound_message_id}, обновление пропущено")
            else:
                logger.warning(f"[WARNING] _metadata не в result или message_log not dict: _metadata={('_metadata' in result)}, is_dict={isinstance(message_log, dict)}")

            # 5. Формируем ответ бота
            bot_response = self._extract_bot_response(result)

            # 6. Логируем исходящее сообщение (ответ бота)
            # ИСПРАВЛЕНО (2025-12-27): Добавляем txtPrb и metadata в outbound сообщения
            if bot_response:
                # ИСПРАВЛЕНО (2026-01-05): Отладочный лог - проверяем result и _metadata
                logger.info(f"[DEBUG] result ключи: {list(result.keys())}")
                logger.info(f"[DEBUG] '_metadata' в result: {'_metadata' in result}")
                if '_metadata' in result:
                    logger.info(f"[DEBUG] _metadata ключи: {list(result['_metadata'].keys())}")
                    logger.info(f"[DEBUG] 'txtPrb' в _metadata: {'txtPrb' in result['_metadata']}")
                    if 'txtPrb' in result['_metadata']:
                        logger.info(f"[DEBUG] txtPrb значение: '{result['_metadata']['txtPrb']}'")

                # Формируем metadata для outbound сообщения
                outbound_metadata = {'service_result': result}

                # ИСПРАВЛЕНО (2026-03-05): Сохраняем api_info и client_system из исходного metadata
                if metadata and isinstance(metadata, dict):
                    logger.info(f"[DEBUG] metadata на входе: {list(metadata.keys())}")
                    if 'api_info' in metadata:
                        outbound_metadata['api_info'] = metadata['api_info']
                        logger.info(f"[DEBUG] ✅ api_info скопирован: {metadata['api_info']}")
                    if 'client_system' in metadata:
                        outbound_metadata['client_system'] = metadata['client_system']
                        logger.info(f"[DEBUG] ✅ client_system скопирован: {metadata['client_system']}")
                else:
                    logger.warning(f"[DEBUG] ⚠️ metadata отсутствует или не dict: type={type(metadata)}, value={metadata}")

                # Добавляем txtPrb если есть в result
                if '_metadata' in result and 'txtPrb' in result['_metadata']:
                    outbound_metadata['txtPrb'] = result['_metadata']['txtPrb']
                    # ИСПРАВЛЕНО (2026-02-24): accumulated_fields УДАЛЁН
                    outbound_metadata['established_filters'] = result['_metadata'].get('established_filters', {})
                    # ИСПРАВЛЕНО (2026-02-04): Добавляем txtStopQ (запрещенные вопросы)
                    outbound_metadata['txtStopQ'] = result['_metadata'].get('txtStopQ', [])
                    logger.info(f"[DEBUG] ✅ txtPrb ДОБАВЛЕН в outbound_metadata: '{outbound_metadata['txtPrb']}'")
                    logger.info(f"[DEBUG] ✅ txtStopQ ДОБАВЛЕН в outbound_metadata: {len(outbound_metadata.get('txtStopQ', []))} вопросов")
                else:
                    logger.warning(f"[WARNING] ⚠️ txtPrb НЕ ДОБАВЛЕН в outbound_metadata!")

                # ИСПРАВЛЕНО (2026-01-06): Логируем outbound для ВСЕХ каналов
                # КРИТИЧЕСКИ ВАЖНО: test_bot_simulator и другие каналы тоже нуждаются в логировании!

                # ИСПРАВЛЕНО (2026-03-04): Завершаем трекинг ДО логирования outbound
                tracer.end("total_request")
                performance_data = tracer.save_to_metadata()

                # ИСПРАВЛЕНО (2026-03-10): Отладочный лог для проверки performance_data
                logger.info(f"[DEBUG] performance_data keys: {list(performance_data.keys()) if performance_data else 'None'}")
                logger.info(f"[DEBUG] performance в performance_data: {'performance' in performance_data if performance_data else False}")
                if performance_data and 'performance' in performance_data:
                    logger.info(f"[DEBUG] performance ключи: {list(performance_data['performance'].keys())}")

                # Добавляем performance данные в outbound_metadata
                if performance_data and 'performance' in performance_data:
                    outbound_metadata['performance'] = performance_data['performance']
                    logger.info(f"[DEBUG] ✅ Performance данные добавлены в outbound_metadata: {len(performance_data.get('performance', {}).get('stages', []))} этапов")
                else:
                    logger.warning(f"[WARNING] ⚠️ Performance данные НЕ добавлены: performance_data={performance_data}")

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
                'service_detected': result.get('service_id') if result.get('status') == 'SUCCESS' else None,
                '_metadata': result.get('_metadata', {}),  # ИСПРАВЛЕНО (2026-02-17): Передаем metadata в финальный ответ
                'performance': performance_data.get('performance', {})  # ИСПРАВЛЕНО (2026-03-04): Добавляем performance данные
            }

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка обработки сообщения: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'session_id': session_id if session_id else f"{channel}_{user_id}"
            }

    async def _find_or_create_active_session(self, user_id: str, channel: str) -> str:
        """
        Ищет активную сессию пользователя (не старше 1 часа) или создает новую

        ИСПРАВЛЕНО (2025-12-28):
        - Проверяет последнюю сессию пользователя
        - Если последняя сессия не старше 1 часа - продолжает её
        - Иначе создает новую сессию

        Args:
            user_id: ID пользователя в канале
            channel: Канал связи

        Returns:
            str: ID сессии (существующей или новой)
        """
        try:
            from message_handler.models import MessageLog
            from django.utils import timezone
            from datetime import timedelta

            def find_session_sync():
                # Ищем последнюю сессию пользователя
                last_msg = MessageLog.objects.filter(
                    user_id=user_id,
                    channel=channel
                ).order_by('-timestamp').first()

                if not last_msg:
                    # Нет сообщений - создаем новую сессию
                    return None

                # Проверяем возраст последнего сообщения
                now = timezone.now()
                session_age = now - last_msg.timestamp

                # Если прошло меньше 1 часа - продолжаем эту сессию
                if session_age < timedelta(hours=1):
                    logger.info(f"Активная сессия найдена: {last_msg.session_id} (возраст: {session_age.seconds // 60} мин)")
                    return last_msg.session_id

                # Сессия устарела - создаем новую
                logger.info(f"Последняя сессия устарела ({session_age.seconds // 60} мин), создаем новую")
                return None

            existing_session_id = await sync_to_async(find_session_sync)()

            if existing_session_id:
                return existing_session_id

            # Создаем новую сессию
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_session_id = f"{channel}_{user_id}_{timestamp}"
            logger.info(f"Создана новая сессия: {new_session_id}")
            return new_session_id

        except Exception as e:
            logger.error(f"Ошибка поиска активной сессии: {e}")
            # Fallback: создаем новую сессию
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{channel}_{user_id}_{timestamp}"

    async def _log_message(
        self,
        text: str,
        user_id: str,
        channel: str,
        message_id: str,
        session_id: str,
        direction: str,
        metadata: Dict = None,
        django_user_id: Optional[int] = None,
        dialog_id: Optional[str] = None,
        confidence_score: Optional[float] = None,
        service_detected_id: Optional[int] = None,
        processing_stage: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cost_rub: Optional[float] = None
    ) -> Dict:
        """
        Логирование сообщения в dialog_logs

        ИСПРАВЛЕНО (2026-01-03): Переписано на использование dialog_logs
        Вместо message_handler_messagelog используем dialog_logs

        Returns:
            Dict: Созданная запись сообщения
        """
        try:
            from dialog_logger_service import get_dialog_logger

            dialog_logger = get_dialog_logger()

            # Конвертируем user_id в int для dialog_logs
            user_id_int = int(user_id) if user_id.isdigit() else 0

            # Определяем message_type
            if direction == 'inbound':
                message_type = 'inbound'
            elif direction == 'outbound':
                message_type = 'outbound'
            else:
                message_type = 'system'

            # ИСПРАВЛЕНО (2026-01-05): Генерируем UUID из session_id если не передан dialog_id
            final_dialog_id = dialog_id
            if not final_dialog_id:
                # Если session_id уже UUID - используем его
                import re
                uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                if re.match(uuid_pattern, session_id.lower()):
                    final_dialog_id = session_id
                else:
                    # Иначе генерируем UUID из session_id (детерминировано)
                    import hashlib
                    session_hash = hashlib.md5(session_id.encode()).hexdigest()
                    final_dialog_id = f"{session_hash[:8]}-{session_hash[8:12]}-{session_hash[12:16]}-{session_hash[16:20]}-{session_hash[20:32]}"

            # ИСПРАВЛЕНО (2026-03-05): Отладочный вывод metadata
            final_metadata = {
                **(metadata or {}),
                'channel': channel,
                'message_id': message_id,
                'django_user_id': django_user_id
            }
            logger.info(f"[DEBUG] _log_message: metadata keys={list(final_metadata.keys())}, api_info={final_metadata.get('api_info')}")

            # Логируем через DialogLoggerService
            # ИСПРАВЛЕНО (2026-01-06): Получаем реальный ID созданной записи
            # ИСПРАВЛЕНО (2026-03-05): Используем final_metadata (с api_info)
            record_id = await dialog_logger.log_message(
                dialog_id=final_dialog_id,  # ИСПРАВЛЕНО: гарантированно UUID
                user_id=user_id_int,
                message_type=message_type,
                message_content=text,
                processing_stage=processing_stage,
                confidence_score=confidence_score,
                service_detected_id=service_detected_id,
                processing_time_ms=processing_time_ms,
                llm_provider=llm_provider,
                llm_model=llm_model,
                tokens_used=tokens_used,
                cost_rub=cost_rub,
                metadata=final_metadata,  # ИСПРАВЛЕНО (2026-03-05): final_metadata вместо {}
                # ИСПРАВЛЕНО (2026-01-05): session_id, channel, direction, message_id ДОЛЖНЫ быть отдельными параметрами!
                session_id=session_id,
                channel=channel,
                direction=direction,
                message_id=message_id,
                django_user_id=django_user_id
            )

            # ИСПРАВЛЕНО (2026-01-06): Возвращаем реальный ID из БД
            return {
                'id': record_id if record_id else 0,
                'created_at': None
            }

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка логирования в dialog_logs: {e}")
            return {}

    async def _update_message_metadata(self, message_id: int, metadata: Dict) -> bool:
        """
        Обновляет metadata для сообщения в dialog_logs

        ИСПРАВЛЕНО (2026-01-06): Добавлено для обновления txtPrb в inbound сообщениях

        Args:
            message_id: ID сообщения в dialog_logs
            metadata: Новые метаданные (будут объединены с существующими)

        Returns:
            bool: True если успешно, False если ошибка
        """
        try:
            from django.db import connection

            def update_sync():
                with connection.cursor() as cursor:
                    # Читаем существующую metadata
                    cursor.execute("""
                        SELECT metadata FROM dialog_logs WHERE id = %s
                    """, [message_id])

                    row = cursor.fetchone()
                    if not row:
                        logger.warning(f"Сообщение id={message_id} не найдено")
                        return False

                    import json
                    existing_metadata = json.loads(row[0]) if row[0] else {}

                    # ИСПРАВЛЕНО (2026-03-05): Сохраняем api_info и client_system при обновлении metadata
                    # Если новые метаданные не содержат эти поля, сохраняем их из существующих
                    preserved_fields = ['api_info', 'client_system']
                    for field in preserved_fields:
                        if field in existing_metadata and field not in metadata:
                            metadata[field] = existing_metadata[field]
                            logger.info(f"[DEBUG] Сохранен {field} при обновлении metadata")

                    # Объединяем метаданные
                    existing_metadata.update(metadata)

                    # Обновляем в БД
                    cursor.execute("""
                        UPDATE dialog_logs
                        SET metadata = %s
                        WHERE id = %s
                    """, [json.dumps(existing_metadata, ensure_ascii=False), message_id])

                    logger.debug(f"Metadata обновлена для сообщения id={message_id}")
                    return True

            result = await sync_to_async(update_sync)()
            return result

        except Exception as e:
            logger.error(f"Ошибка обновления metadata для сообщения {message_id}: {e}")
            return False

    async def _get_dialog_history(self, session_id: str, limit: int = 10) -> list:
        """
        Получить историю диалога из БД

        ИСПРАВЛЕНО (2026-01-05): Использует raw SQL вместо ORM
        ORM кеш не обновляется после raw SQL INSERT в DialogLoggerService!

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
            from django.db import connection

            def get_history_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО (2026-01-05): Добавляем metadata в SELECT для txtPrb
                    cursor.execute("""
                        SELECT direction, message_content, timestamp, metadata
                        FROM dialog_logs
                        WHERE session_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, [session_id, limit])

                    messages = []
                    for row in cursor.fetchall():
                        # Парсим metadata если это строка
                        metadata = row[3]
                        if isinstance(metadata, str):
                            try:
                                import json
                                metadata = json.loads(metadata)
                            except:
                                metadata = {}

                        messages.append({
                            'role': 'user' if row[0] == 'inbound' else 'bot',
                            'text': row[1],
                            'timestamp': row[2].isoformat(),
                            'metadata': metadata if isinstance(metadata, dict) else {}
                        })

                    # Разворачиваем список (сначала старые сообщения)
                    return list(reversed(messages))

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

            # ИСПРАВЛЕНО (2026-03-04): Проверка на строку "null"
            if message and message != "null":
                return message
            # ИСПРАВЛЕНИЕ (2026-01-12): По правилу 7 CLAUDE.md - только открытые вопросы!
            # ЗАПРЕЩЕНО: "Это правильно?" - закрытый вопрос
            return f"Поняла вас: {service_name}. Опишите подробнее детали, если нужно."

        elif status == 'CONFIRMED':
            # ИСПРАВЛЕНО (2025-12-25): Пользователь подтвердил услугу
            message = result.get('message')
            # ИСПРАВЛЕНО (2026-03-04): Проверка на строку "null"
            if message and message != "null":
                return message

            service_name = result.get('service_name', 'услуга')
            return f"Спасибо за подтверждение. Заявка создана на услугу: {service_name}"

        elif status == 'REJECTED':
            # ИСПРАВЛЕНО (2025-12-25): Пользователь отрицал
            message = result.get('message')
            # ИСПРАВЛЕНО (2026-03-04): Проверка на строку "null"
            if message and message != "null":
                return message
            return "Понял, уточните пожалуйста что именно у вас проблема?"

        elif status == 'AMBIGUOUS':
            # Нужен уточняющий вопрос
            message = result.get('message')

            # ИСПРАВЛЕНО (2026-03-04): Проверка на строку "null" (JSON null при чтении из БД)
            # PostgreSQL JSONB ->> operator возвращает "null" как строку для JSON null
            if message and message != "null":
                return message

            # Если нет message или message == "null", используем список кандидатов
            candidates = result.get('candidates', [])
            if candidates:
                # ИСПРАВЛЕНИЕ (2026-01-12): По правилу 7 CLAUDE.md - только открытые вопросы!
                # ЗАПРЕЩЕНО: "это X, Y, Z?" - перечисление + закрытый вопрос
                # ПРАВИЛЬНО: открытый вопрос без перечисления
                # ИСПРАВЛЕНИЕ (2026-02-14): Fallback вопрос закомментирован
                # return "Опишите подробнее, что именно произошло?"
                pass  # MainAgent сам должен сгенерировать вопрос

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

            # ИСПРАВЛЕНИЕ (2026-01-12): Проверяем открытые вопросы ("Похоже на проблему", "Опишите подробнее")
            # Старые закрытые вопросы больше не используются по правилу 7 CLAUDE.md
            has_clarification_question = (
                'похоже на' in last_bot_text.lower() or
                'опишите подробнее' in last_bot_text.lower() or
                'уточните детали' in last_bot_text.lower() or
                # Для обратной совместимости со старыми диалогами
                'правильно ли я понял' in last_bot_text.lower()
            )

            if not has_clarification_question:
                return {'is_confirmation_response': False}

            # Это ответ на уточняющий вопрос - проверяем что ответил пользователь
            text_lower = text.lower().strip()

            # ИСПРАВЛЕНИЕ (2026-01-12): Обработка неопределенных ответов
            # "не знаю", "возможно", "не уверен" - передаем в MainAgent для дополнительного анализа
            uncertain_responses = ['не знаю', 'не уверен', 'возможно', 'хз', 'может быть', 'точно не знаю']
            if any(resp in text_lower for resp in uncertain_responses):
                logger.info(f"MessageHandler: Неопределенный ответ: '{text}' - передаем в MainAgent")
                # НЕ помечаем как confirmation_response, даем MainAgent обработать
                return {'is_confirmation_response': False, 'is_uncertain': True}

            # ПОДТВЕРЖДЕНИЕ (пользователь явно подтверждает)
            if text_lower in ['да', 'верно', 'правильно', 'то самое', 'ага', 'yes', 'подтверждаю']:
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
                        'message': f"Спасибо. Создаю заявку: {service_name}",
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

            # ОТРИЦАНИЕ (пользователь явно отрицает)
            elif text_lower in ['нет', 'неправильно', 'не то', 'нет не то', 'no', 'неверно']:
                logger.info(f"MessageHandler: Обнаружено отрицание '{text}'")

                result = {
                    'status': 'REJECTED',
                    'message': "Понял. Опишите вашу проблему подробнее, чтобы я мог правильно помочь."
                }

                return {
                    'is_confirmation_response': True,
                    'result': result
                }

            # Другой ответ - передаем в MainAgent как обычное сообщение
            else:
                logger.info(f"MessageHandler: Ответ на уточнение: '{text}' - передаем в MainAgent")
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
                ).order_by('-timestamp').first()  # ИСПРАВЛЕНО: было created_at

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
        ИСПРАВЛЕНО (2026-01-12): Обновлено для открытых вопросов

        Args:
            dialog_history: История диалога

        Returns:
            Dict: Mock service_result или None
        """
        try:
            # ИСПРАВЛЕНИЕ (2026-01-12): Проверяем открытые вопросы ("Похоже на проблему: ...")
            for msg in reversed(dialog_history):
                if msg.get('role') == 'bot':
                    text = msg.get('text', '')
                    # Ищем название услуги после "Похоже на проблему:" или "Правильно ли я понял, что у вас:"
                    import re
                    # Новый формат: "Похоже на проблему: X. Опишите подробнее..."
                    match_new = re.search(r'Похоже на проблему[:\s]+([^.]+)', text, re.IGNORECASE)
                    # Старый формат (для обратной совместимости): "Правильно ли я понял, что у вас: X?"
                    match_old = re.search(r'что у вас[:\s]+([^.]+)', text, re.IGNORECASE)

                    service_name = None
                    if match_new:
                        service_name = match_new.group(1).strip()
                    elif match_old:
                        service_name = match_old.group(1).strip()

                    if service_name:
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
                ).order_by('timestamp')[:limit]  # ИСПРАВЛЕНО: было created_at

                return [
                    {
                        'id': msg.id,
                        'channel': msg.get_channel_display(),
                        'direction': msg.get_direction_display(),
                        'text': msg.message_content,  # ИСПРАВЛЕНО: было msg.text
                        'timestamp': msg.timestamp.isoformat(),  # ИСПРАВЛЕНО: было msg.created_at
                        'metadata': msg.metadata
                    }
                    for msg in messages
                ]

            return await sync_to_async(get_messages_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: Ошибка получения сообщений сессии: {e}")
            return []

    async def log_outbound_message(
        self,
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        metadata: Dict = None
    ) -> Dict:
        """
        Публичный метод для логирования исходящих сообщений (Bot -> User)

        Используется ботами (Telegram, WhatsApp) для логирования ответов пользователям.

        Args:
            text: Текст исходящего сообщения
            user_id: ID пользователя в канале
            channel: Канал связи (telegram, whatsapp, web, etc)
            session_id: ID сессии диалога
            metadata: Дополнительные метаданные (txtPrb, filters, etc)

        Returns:
            Dict: Результат логирования
        """
        try:
            # Генерируем message_id для outbound
            import uuid
            message_id = str(uuid.uuid4())

            # Логируем через внутренний метод
            result = await self._log_message(
                text=text,
                user_id=user_id,
                channel=channel,
                message_id=message_id,
                session_id=session_id,
                direction='outbound',
                metadata=metadata or {}
            )

            logger.info(f"✅ Outbound сообщение записано: session_id={session_id}, text='{text[:50]}...'")
            return {'status': 'success', 'message_log_id': result.get('id')}

        except Exception as e:
            logger.error(f"❌ Ошибка логирования outbound сообщения: {e}")
            return {'status': 'error', 'error': str(e)}
