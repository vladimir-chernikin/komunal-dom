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


class CommunicativeScript(models.Model):
    """Коммуникативный скрипт для бота"""

    SCRIPT_TYPES = [
        ('fallback', 'Fallback при ошибке AI'),
        ('pause', 'Заполнение паузы (audio)'),
        ('greeting', 'Приветствие'),
        ('clarification', 'Уточняющий вопрос'),
        ('confirmation', 'Подтверждение'),
        ('error', 'Сообщение об ошибке'),
    ]

    CHANNELS = [
        ('telegram', 'Telegram'),
        ('audio', 'Аудио (телефон)'),
        ('both', 'Оба канала'),
    ]

    script_name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Название скрипта'
    )

    script_type = models.CharField(
        max_length=50,
        choices=SCRIPT_TYPES,
        db_index=True,
        verbose_name='Тип скрипта'
    )

    channel = models.CharField(
        max_length=50,
        choices=CHANNELS,
        db_index=True,
        verbose_name='Канал связи'
    )

    text = models.TextField(
        verbose_name='Текст скрипта'
    )

    conditions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Условия использования',
        help_text='JSON условия для triggerа'
    )

    priority = models.FloatField(
        default=1.0,
        verbose_name='Приоритет'
    )

    max_uses_per_day = models.IntegerField(
        default=-1,
        verbose_name='Макс. использований/день',
        help_text='-1 = без ограничений'
    )

    min_dialog_turn = models.IntegerField(
        default=0,
        verbose_name='Мин. номер хода'
    )

    max_dialog_turn = models.IntegerField(
        default=-1,
        verbose_name='Макс. номер хода',
        help_text='-1 = без ограничений'
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name='Активен'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Создан'
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Обновлен'
    )

    category = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Категория'
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name='Заметки'
    )

    class Meta:
        verbose_name = 'Коммуникативный скрипт'
        verbose_name_plural = 'Коммуникативные скрипты'
        ordering = ['script_type', '-priority', 'script_name']
        indexes = [
            models.Index(fields=['script_type']),
            models.Index(fields=['channel']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.script_name} ({self.get_script_type_display()})"
