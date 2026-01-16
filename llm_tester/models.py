#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модели для LLM Tester - приложения для тестирования промптов
"""

from django.db import models


class PromptTemplate(models.Model):
    """
    Шаблон промпта для LLM тестирования
    """
    PROMPT_TYPES = [
        ('filter_detection', 'FilterDetectionService'),
        ('main_agent', 'MainAgent'),
        ('custom', 'Кастомный'),
    ]

    # Поля
    name = models.CharField(max_length=200, verbose_name='Название промпта')
    slug = models.SlugField(max_length=100, unique=True, verbose_name='Slug')
    prompt_type = models.CharField(
        max_length=50,
        choices=PROMPT_TYPES,
        verbose_name='Тип промпта'
    )
    template = models.TextField(verbose_name='Шаблон промпта (с переменными)')

    # Метаданные
    description = models.TextField(blank=True, verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        verbose_name = 'Шаблон промпта'
        verbose_name_plural = 'Шаблоны промптов'
        ordering = ['prompt_type', 'name']

    def __str__(self):
        return f"{self.get_prompt_type_display()}: {self.name}"

    def get_variables(self):
        """Возвращает список переменных из шаблона"""
        import re
        # Ищем переменные в формате {variable_name}
        variables = re.findall(r'\{(\w+)\}', self.template)
        return sorted(set(variables))


class PromptPreset(models.Model):
    """
    Пресет промпта с предустановленными значениями переменных
    """
    prompt = models.ForeignKey(
        PromptTemplate,
        on_delete=models.CASCADE,
        related_name='presets',
        verbose_name='Шаблон промпта'
    )
    name = models.CharField(max_length=200, verbose_name='Название пресета')
    variable_values = models.JSONField(verbose_name='Значения переменных (JSON)')

    # Метаданные
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'Пресет промпта'
        verbose_name_plural = 'Пресеты промптов'
        ordering = ['prompt', 'name']

    def __str__(self):
        return f"{self.prompt.name} - {self.name}"


class LLMTestResult(models.Model):
    """
    Результат тестирования LLM
    """
    PROVIDERS = [
        ('yandexgpt', 'YandexGPT'),
        ('gigachat', 'GigaChat'),
    ]

    MODELS = {
        'yandexgpt': [
            ('lite', 'YandexGPT Lite'),
            ('pro', 'YandexGPT Pro'),
        ],
        'gigachat': [
            ('GigaChat', 'GigaChat'),
            ('GigaChat-2', 'GigaChat-2'),
            ('GigaChat-Plus', 'GigaChat-Plus'),
            ('GigaChat-2.1', 'GigaChat-2.1'),
        ],
    }

    # Связь с пресетом
    preset = models.ForeignKey(
        PromptPreset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='test_results',
        verbose_name='Использованный пресет'
    )

    # Параметры запроса
    provider = models.CharField(max_length=20, choices=PROVIDERS, verbose_name='Провайдер')
    model = models.CharField(max_length=50, verbose_name='Модель')
    prompt_text = models.TextField(verbose_name='Отправленный промпт')

    # Результат
    response_text = models.TextField(verbose_name='Ответ LLM')

    # Метаданные использования
    usage_info = models.JSONField(verbose_name='Информация об использовании (токены, стоимость)')

    # Статус
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Успех'),
            ('error', 'Ошибка'),
        ],
        default='success',
        verbose_name='Статус'
    )
    error_message = models.TextField(blank=True, verbose_name='Сообщение об ошибке')

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Создал'
    )

    class Meta:
        verbose_name = 'Результат теста LLM'
        verbose_name_plural = 'Результаты тестов LLM'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_provider_display()} - {self.model} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"
