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
