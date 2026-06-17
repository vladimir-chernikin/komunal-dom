#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модели для логирования сообщений из всех каналов связи
"""

from django.db import models
from django.contrib.auth import get_user_model


class MessageLog(models.Model):
    """
    Лог всех сообщений от пользователей и ответов бота

    ИСПРАВЛЕНО (2026-01-05): Использует таблицу dialog_logs вместо message_handler_messagelog
    Модель指向 на существующую таблицу dialog_logs через Meta.db_table
    """

    # Каналы связи
    CHANNEL_CHOICES = [
        ('telegram', 'Telegram'),
        ('whatsapp', 'WhatsApp'),
        ('maxchat', 'Мессенджер Макс'),
        ('web', 'Веб-сайт'),
        ('test_bot', 'Тестовый бот-имитатор'),
        ('transcriber', 'Голосовой транскрибатор'),
        ('api', 'Внешнее API'),  # ИСПРАВЛЕНО (2026-02-24): Добавлен для внешних интеграций
    ]

    # Направление сообщения
    DIRECTION_CHOICES = [
        ('inbound', 'Входящее (от пользователя)'),
        ('outbound', 'Исходящее (от бота)'),
        ('system', 'Системное'),
    ]

    # Тип сообщения
    MESSAGE_TYPE_CHOICES = [
        ('inbound', 'Входящее'),
        ('outbound', 'Исходящее'),
        ('system', 'Системное'),
    ]

    # Основные поля (соответствуют таблице dialog_logs)
    dialog_id = models.UUIDField(
        verbose_name='ID диалога'
    )
    channel = models.CharField(
        max_length=50,
        choices=CHANNEL_CHOICES,
        db_index=True,
        verbose_name='Канал связи'
    )
    direction = models.CharField(
        max_length=20,
        choices=DIRECTION_CHOICES,
        db_index=True,
        verbose_name='Направление'
    )
    message_id = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='ID сообщения в канале'
    )
    session_id = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='ID сессии диалога'
    )

    # Пользователь
    user_id = models.IntegerField(
        db_index=True,
        verbose_name='ID пользователя в канале'
    )
    django_user_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='ID пользователя Django'
    )

    # Содержание сообщения
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE_CHOICES,
        db_index=True,
        verbose_name='Тип сообщения'
    )
    message_content = models.TextField(
        verbose_name='Текст сообщения'
    )

    # Определение услуги
    processing_stage = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='Стадия обработки'
    )
    confidence_score = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Уверенность определения'
    )
    service_detected_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='ID определенной услуги'
    )

    # Адрес
    address_extracted = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Извлеченный адрес'
    )

    # Метрики производительности
    processing_time_ms = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Время обработки (мс)'
    )

    # LLM метрики
    llm_provider = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name='LLM провайдер'
    )
    llm_model = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='LLM модель'
    )
    tokens_used = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Количество токенов'
    )
    cost_rub = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Стоимость (руб)'
    )

    # Метаданные
    metadata = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Метаданные',
        help_text='Дополнительная информация (service_detection, txtPrb, filters и т.д.)'
    )

    # Время создания
    timestamp = models.DateTimeField(
        db_index=True,
        verbose_name='Время получения'
    )

    class Meta:
        verbose_name = 'Лог сообщения'
        verbose_name_plural = 'Логи сообщений'
        ordering = ['-timestamp']
        db_table = 'dialog_logs'  # ИСПРАВЛЕНИЕ (2026-01-05): Используем существующую таблицу
        indexes = [
            models.Index(fields=['channel', 'timestamp']),
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(fields=['user_id', 'channel']),
            models.Index(fields=['dialog_id']),
            models.Index(fields=['message_type']),
        ]

    def __str__(self):
        direction_icon = '→' if self.direction == 'inbound' else '←'
        return f"{direction_icon} {self.get_channel_display()} | {self.user_id} | {self.message_content[:50]}"

    def get_context_history(self, limit=10):
        """
        Получить историю диалога для этого сообщения

        ИСПРАВЛЕНО (2026-01-05): Использует message_content и timestamp вместо text и created_at

        Returns:
            list: Список предыдущих сообщений в этой сессии
        """
        messages = MessageLog.objects.filter(
            session_id=self.session_id,
            timestamp__lt=self.timestamp
        ).order_by('-timestamp')[:limit]

        # Конвертируем в формат для LLM
        return [
            {
                'role': 'user' if msg.direction == 'inbound' else 'bot',
                'text': msg.message_content,
                'timestamp': msg.timestamp.isoformat(),
                'channel': msg.channel
            }
            for msg in reversed(messages)
        ]



class APIErrorLog(models.Model):
    """
    Лог ошибочных запросов к внешнему API

    ИСПОЛЬЗОВАНИЕ (2026-03-05):
    - Логирование всех ошибок в send_message_external
    - Поиск по дате, IP, session_id, client_system
    - Анализ проблем с интеграциями
    """

    # Типы ошибок
    ERROR_TYPE_CHOICES = [
        ('auth', 'Ошибка аутентификации'),
        ('validation', 'Ошибка валидации'),
        ('processing', 'Ошибка обработки'),
        ('timeout', 'Таймаут'),
        ('internal', 'Внутренняя ошибка'),
    ]

    # Тип ошибки
    error_type = models.CharField(
        max_length=50,
        choices=ERROR_TYPE_CHOICES,
        db_index=True,
        verbose_name='Тип ошибки'
    )

    # HTTP статус код
    status_code = models.IntegerField(
        db_index=True,
        verbose_name='HTTP статус'
    )

    # Краткое описание ошибки
    error_message = models.CharField(
        max_length=500,
        db_index=True,
        verbose_name='Ошибка'
    )

    # Детали ошибки (traceback)
    error_details = models.TextField(
        blank=True,
        null=True,
        verbose_name='Детали ошибки'
    )

    # Идентификаторы запроса
    session_id = models.CharField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
        verbose_name='Session ID'
    )

    request_id = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Request ID'
    )

    # Клиентская информация
    client_ip = models.GenericIPAddressField(
        db_index=True,
        null=True,
        blank=True,
        verbose_name='IP клиента'
    )

    client_system = models.CharField(
        max_length=100,
        db_index=True,
        null=True,
        blank=True,
        verbose_name='Клиентская система'
    )

    token_preview = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Токен (первые символы)'
    )

    # Данные запроса
    request_data = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Данные запроса',
        help_text='JSON тело запроса'
    )

    message_preview = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Сообщение (первые символы)'
    )

    # Дополнительная информация
    user_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='User ID'
    )

    nomer = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        verbose_name='NOMER (абонент)'
    )

    # Время
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Время ошибки'
    )

    class Meta:
        verbose_name = 'Лог ошибок API'
        verbose_name_plural = 'Логи ошибок API'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['timestamp', 'status_code']),
            models.Index(fields=['client_ip', 'timestamp']),
            models.Index(fields=['session_id', 'timestamp']),
            models.Index(fields=['client_system', 'timestamp']),
            models.Index(fields=['error_type', 'timestamp']),
            models.Index(fields=['nomer']),
        ]

    def __str__(self):
        return f"{self.get_error_type_display()} | {self.client_ip} | {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class VoiceCallSession(models.Model):
    """Voice API session lifecycle for Asterisk integrations."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('ended', 'Ended'),
    ]

    session_id = models.CharField(max_length=255, unique=True, db_index=True)
    schema_version = models.CharField(max_length=32, default='asterisk_voice_v2.1')
    source = models.CharField(max_length=50, default='asterisk')
    channel = models.CharField(max_length=50, default='voice')
    user_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    direction = models.CharField(max_length=20, null=True, blank=True)
    client_phone = models.CharField(max_length=40, blank=True)
    company_phone = models.CharField(max_length=40, blank=True)
    asterisk_channel_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    end_reason = models.CharField(max_length=40, blank=True)
    call_payload = models.JSONField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'message_handler_voice_call_sessions'
        verbose_name = 'Voice call session'
        verbose_name_plural = 'Voice call sessions'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['session_id', 'status']),
            models.Index(fields=['client_phone', 'updated_at']),
            models.Index(fields=['asterisk_channel_id']),
        ]

    def __str__(self):
        return f"{self.session_id} | {self.status}"


class VoiceTurnRevision(models.Model):
    """Latest accepted revision for one voice turn within one session."""

    session_id = models.CharField(max_length=255, db_index=True)
    turn_id = models.CharField(max_length=255, db_index=True)
    latest_revision = models.PositiveIntegerField(default=0)
    obsolete_revisions = models.JSONField(default=list, blank=True)
    supersedes_revision = models.PositiveIntegerField(null=True, blank=True)
    schema_version = models.CharField(max_length=32, default='asterisk_voice_v2.1')
    user_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    message_preview = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'message_handler_voice_turn_revisions'
        verbose_name = 'Voice turn revision'
        verbose_name_plural = 'Voice turn revisions'
        ordering = ['-updated_at']
        unique_together = [('session_id', 'turn_id')]
        indexes = [
            models.Index(fields=['session_id', 'turn_id']),
            models.Index(fields=['session_id', 'updated_at']),
            models.Index(fields=['user_id', 'updated_at']),
        ]

    def __str__(self):
        return f"{self.session_id} | {self.turn_id} | rev {self.latest_revision}"
