#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модели для LLM Tester - приложения для тестирования промптов
"""

from django.db import models


class PromptTemplate(models.Model):
    """
    Шаблоны промптов для тестирования микросервисов (FilterDetectionService, MainAgent)
    """

    PROMPT_TYPES = [
        ('filter_detection', 'FilterDetectionService'),
        ('main_agent', 'MainAgent'),
        ('problem_accumulation', 'ProblemAccumulationService'),
        ('custom', 'Кастомный'),
    ]

    # Поля
    name = models.CharField(
        max_length=200,
        verbose_name='Название промпта',
        help_text='Название микросервиса или промпта'
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name='Slug',
        help_text='Уникальный идентификатор для URL'
    )
    prompt_type = models.CharField(
        max_length=50,
        choices=PROMPT_TYPES,
        verbose_name='Тип промпта',
        help_text='Какой микросервис использует этот промпт'
    )
    template = models.TextField(
        verbose_name='Шаблон промпта',
        help_text='Текст промпта с переменными в формате {variable_name}'
    )

    # Метаданные
    description = models.TextField(
        blank=True,
        verbose_name='Описание',
        help_text='Для чего используется этот шаблон'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен',
        help_text='Используется ли этот шаблон для тестирования'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        verbose_name = 'AI и Промпты: Шаблон промпта'
        verbose_name_plural = 'AI и Промпты: Шаблоны промптов'
        ordering = ['prompt_type', 'name']
        app_label = 'portal'  # Группировка в раздел УК Аспект (Ольга:Рефакторинг 09.02.2026)

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
    Тестовые пресеты на базе шаблонов для экспериментов с промптами
    """
    prompt = models.ForeignKey(
        PromptTemplate,
        on_delete=models.CASCADE,
        related_name='presets',
        verbose_name='Шаблон промпта',
        help_text='Базовый шаблон для этого пресета'
    )
    name = models.CharField(
        max_length=200,
        verbose_name='Название пресета',
        help_text='Название варианта теста'
    )
    variable_values = models.JSONField(
        verbose_name='Значения переменных',
        help_text='JSON с подстановками для переменных шаблона'
    )
    custom_prompt = models.TextField(
        blank=True,
        verbose_name='Измененный текст промпта',
        help_text='Если заполнено - заменяет шаблон'
    )

    # Метаданные
    is_active = models.BooleanField(
        default=True,
        verbose_name='Активен',
        help_text='Используется ли этот пресет для тестирования'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'AI и Промпты: Тестовый пресет'
        verbose_name_plural = 'AI и Промпты: Тестовые пресеты'
        ordering = ['prompt', 'name']
        app_label = 'portal'  # Группировка в раздел УК Аспект (Ольга:Рефакторинг 09.02.2026)

    def __str__(self):
        return f"{self.prompt.name} - {self.name}"


class LLMTestResult(models.Model):
    """
    Результаты тестирования LLM моделей (YandexGPT, GigaChat)
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
        verbose_name='Использованный пресет',
        help_text='Какой пресет был протестирован'
    )

    # Параметры запроса
    provider = models.CharField(
        max_length=20,
        choices=PROVIDERS,
        verbose_name='Провайдер',
        help_text='LLM провайдер (YandexGPT, GigaChat)'
    )
    model = models.CharField(
        max_length=50,
        verbose_name='Модель',
        help_text='Название модели (например: YandexGPT Pro, GigaChat-2)'
    )
    prompt_text = models.TextField(
        verbose_name='Отправленный промпт',
        help_text='Полный текст промпта который был отправлен'
    )

    # Результат
    response_text = models.TextField(
        verbose_name='Ответ LLM',
        help_text='Ответ который вернула модель'
    )

    # Метаданные использования
    usage_info = models.JSONField(
        verbose_name='Метрики',
        help_text='Токены, стоимость, время обработки (JSON)'
    )

    # Статус
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Успех'),
            ('error', 'Ошибка'),
        ],
        default='success',
        verbose_name='Статус',
        help_text='Успешно ли выполнен запрос'
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='Сообщение об ошибке',
        help_text='Текст ошибки если статус = error'
    )

    # Метаданные
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Создал',
        help_text='Кто запустил тест'
    )

    class Meta:
        verbose_name = 'AI и Промпты: Результат теста LLM'
        verbose_name_plural = 'AI и Промпты: Результаты тестов LLM'
        ordering = ['-created_at']
        app_label = 'portal'  # Группировка в раздел УК Аспект (Ольга:Рефакторинг 09.02.2026)

    def __str__(self):
        return f"{self.get_provider_display()} - {self.model} - {self.created_at.strftime('%d.%m.%Y %H:%M')}"
