"""
DialogLoggerService - Сервис логирования диалогов в БД

Логирует все сообщения в таблицу dialog_logs:
- Входящие сообщения от пользователей
- Исходящие сообщения от бота
- Вызовы LLM (промпты и ответы)

Правила:
- Все диалоги должны логироваться в dialog_logs
- Все LLM запросы через AIAgentService → llm_request_log
- Логирование в файлы запрещено
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class DialogLoggerService:
    """Сервис логирования диалогов в БД"""

    async def log_message(
        self,
        dialog_id: str,
        user_id: int,
        message_type: str,  # inbound, outbound, system
        message_content: str,
        processing_stage: Optional[str] = None,
        confidence_score: Optional[float] = None,
        service_detected_id: Optional[int] = None,
        address_extracted: Optional[Dict] = None,
        processing_time_ms: Optional[int] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cost_rub: Optional[float] = None,
        metadata: Optional[Dict] = None,
        channel: Optional[str] = None,
        direction: Optional[str] = None,
        message_id: Optional[str] = None,
        session_id: Optional[str] = None,
        django_user_id: Optional[int] = None
    ):
        """
        Логировать сообщение в dialog_logs

        ИСПРАВЛЕНО (2026-01-03): Добавлены поля channel, direction, message_id, session_id, django_user_id

        Args:
            dialog_id: UUID диалога
            user_id: ID пользователя
            message_type: Тип сообщения (inbound, outbound, system)
            message_content: Текст сообщения
            processing_stage: Стадия обработки (optional)
            confidence_score: Уверенность определения услуги (optional)
            service_detected_id: ID определенной услуги (optional)
            address_extracted: Извлеченный адрес (optional)
            processing_time_ms: Время обработки в мс (optional)
            llm_provider: Провайдер LLM (optional)
            llm_model: Модель LLM (optional)
            tokens_used: Количество токенов (optional)
            cost_rub: Стоимость в рублях (optional)
            metadata: Дополнительные метаданные (optional)
            channel: Канал связи (telegram, web, etc) - ИСПРАВЛЕНО 2026-01-03
            direction: Направление (inbound, outbound, system) - ИСПРАВЛЕНО 2026-01-03
            message_id: ID сообщения в канале - ИСПРАВЛЕНО 2026-01-03
            session_id: ID сессии - ИСПРАВЛЕНО 2026-01-03
            django_user_id: ID пользователя Django - ИСПРАВЛЕНО 2026-01-03
        """
        try:
            # ИСПРАВЛЕНИЕ (2026-01-05): Конвертируем dict в JSON для PostgreSQL
            import json

            # Конвертируем dict параметры в JSON строки
            address_extracted_json = json.dumps(address_extracted, ensure_ascii=False) if address_extracted else None
            metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

            from django.db import transaction

            def save_sync():
                # ИСПРАВЛЕНО (2026-01-05): Используем transaction.atomic() для consistency
                try:
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO dialog_logs (
                                    dialog_id,
                                    user_id,
                                    message_type,
                                    message_content,
                                    processing_stage,
                                    confidence_score,
                                    service_detected_id,
                                    address_extracted,
                                    processing_time_ms,
                                    llm_provider,
                                    llm_model,
                                    tokens_used,
                                    cost_rub,
                                    metadata,
                                    timestamp,
                                    channel,
                                    direction,
                                    message_id,
                                    session_id,
                                    django_user_id
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s
                                )
                                RETURNING id
                            """, [
                                dialog_id,
                                user_id,
                                message_type,
                                message_content[:10000],  # Ограничиваем длину
                                processing_stage,
                                confidence_score,
                                service_detected_id,
                                address_extracted_json,  # ИСПРАВЛЕНО: JSON строка
                                processing_time_ms,
                                llm_provider,
                                llm_model,
                                tokens_used,
                                cost_rub,
                                metadata_json,  # ИСПРАВЛЕНО: JSON строка
                                channel,
                                direction or message_type,  # Используем message_type как fallback
                                message_id,
                                session_id,
                                django_user_id
                            ])

                            # ИСПРАВЛЕНО (2026-01-06): Получаем ID ВНУТРИ блока with cursor (пока cursor открыт!)
                            record_id = cursor.fetchone()[0]

                            # ИСПРАВЛЕНО (2026-01-05): Отладочный лог
                            import logging
                            logger_debug = logging.getLogger(__name__)
                            logger_debug.info(f"[DialogLogger] INSERT выполнен: id={record_id}, session_id={session_id}, type={message_type}, direction={direction}")

                            return record_id

                except Exception as e:
                    import logging
                    logger_err = logging.getLogger(__name__)
                    logger_err.error(f"[DialogLogger] ОКАЗАНИЕСЬ ОШИБКА при INSERT: {e}")
                    raise

            # ИСПРАВЛЕНО (2026-01-06): save_sync теперь возвращает ID
            record_id = await sync_to_async(save_sync)()
            logger.debug(f"DialogLogger: сообщение записано и закоммичено (id={record_id}, dialog_id={dialog_id}, type={message_type})")

            return record_id if record_id else None

        except Exception as e:
            logger.error(f"DialogLogger: ошибка записи сообщения: {e}")
            # Не прерываем работу если логирование не удалось

    async def log_incoming_message(
        self,
        dialog_id: str,
        user_id: int,
        message_text: str,
        metadata: Optional[Dict] = None
    ):
        """Логировать входящее сообщение от пользователя"""
        await self.log_message(
            dialog_id=dialog_id,
            user_id=user_id,
            message_type='inbound',
            message_content=message_text,
            metadata=metadata
        )

    async def log_outgoing_message(
        self,
        dialog_id: str,
        user_id: int,
        message_text: str,
        confidence_score: Optional[float] = None,
        service_detected_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ):
        """Логировать исходящее сообщение от бота"""
        await self.log_message(
            dialog_id=dialog_id,
            user_id=user_id,
            message_type='outbound',
            message_content=message_text,
            confidence_score=confidence_score,
            service_detected_id=service_detected_id,
            metadata=metadata
        )

    async def log_llm_request(
        self,
        dialog_id: str,
        user_id: int,
        prompt: str,
        response: str,
        provider: str,
        model: str,
        tokens_used: int,
        cost_rub: float,
        processing_stage: str,
        metadata: Optional[Dict] = None
    ):
        """
        Логировать запрос к LLM

        ВАЖНО: AIAgentService сам пишет в llm_request_log,
        а этот метод пишет в dialog_logs для связки с диалогом.
        """
        await self.log_message(
            dialog_id=dialog_id,
            user_id=user_id,
            message_type='system',
            message_content=f"LLM Request ({provider}/{model}):\nPROMPT: {prompt[:500]}\nRESPONSE: {response[:500]}",
            processing_stage=processing_stage,
            llm_provider=provider,
            llm_model=model,
            tokens_used=tokens_used,
            cost_rub=cost_rub,
            metadata=metadata
        )

    async def log_service_detection(
        self,
        dialog_id: str,
        user_id: int,
        status: str,
        service_id: Optional[int],
        confidence: float,
        candidates: list,
        processing_time_ms: int,
        metadata: Optional[Dict] = None
    ):
        """Логировать результат определения услуги"""
        content = f"Service Detection: {status}"
        if service_id:
            content += f", Service ID: {service_id}"
        content += f", Confidence: {confidence:.2f}"
        if candidates:
            content += f", Candidates: {len(candidates)}"

        await self.log_message(
            dialog_id=dialog_id,
            user_id=user_id,
            message_type='system',
            message_content=content,
            processing_stage='service_detection',
            confidence_score=confidence,
            service_detected_id=service_id,
            processing_time_ms=processing_time_ms,
            metadata=metadata or {'candidates': candidates[:5]}  # Первые 5 кандидатов
        )


# Глобальный экземпляр сервиса
_dialog_logger_instance = None

def get_dialog_logger() -> DialogLoggerService:
    """Получить глобальный экземпляр DialogLoggerService"""
    global _dialog_logger_instance
    if _dialog_logger_instance is None:
        _dialog_logger_instance = DialogLoggerService()
        logger.info("DialogLoggerService инициализирован")
    return _dialog_logger_instance
