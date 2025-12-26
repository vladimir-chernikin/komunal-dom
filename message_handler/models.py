#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модели для логирования сообщений из всех каналов связи
"""

from django.db import models
from django.contrib.auth import get_user_model


class MessageLog(models.Model):
    """Лог всех сообщений от пользователей и ответов бота"""

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
    ]

    # Основные поля
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        db_index=True,
        verbose_name='Канал связи'
    )
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        db_index=True,
        verbose_name='Направление'
    )

    # Идентификаторы
    message_id = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='ID сообщения в канале'
    )
    user_id = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='ID пользователя в канале'
    )
    session_id = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='ID сессии диалога',
        help_text='Уникальный идентификатор диалога'
    )

    # Содержание сообщения
    text = models.TextField(
        verbose_name='Текст сообщения'
    )

    # Метаданные
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Метаданные',
        help_text='Дополнительная информация от канала связи'
    )

    # Время создания
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Время получения'
    )

    # Связь с пользователем Django (если есть)
    django_user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Пользователь Django'
    )

    class Meta:
        verbose_name = 'Лог сообщения'
        verbose_name_plural = 'Логи сообщений'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['channel', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
            models.Index(fields=['user_id', 'channel']),
        ]

    def __str__(self):
        direction_icon = '→' if self.direction == 'inbound' else '←'
        return f"{direction_icon} {self.get_channel_display()} | {self.user_id} | {self.text[:50]}"

    def get_context_history(self, limit=10):
        """
        Получить историю диалога для этого сообщения

        Returns:
            list: Список предыдущих сообщений в этой сессии
        """
        messages = MessageLog.objects.filter(
            session_id=self.session_id,
            created_at__lt=self.created_at
        ).order_by('-created_at')[:limit]

        # Конвертируем в формат для LLM
        return [
            {
                'role': 'user' if msg.direction == 'inbound' else 'bot',
                'text': msg.text,
                'timestamp': msg.created_at.isoformat(),
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
