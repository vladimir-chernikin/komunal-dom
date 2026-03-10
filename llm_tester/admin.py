#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Admin интерфейс для LLM Tester
"""

from django.contrib import admin
from .models import PromptTemplate, PromptPreset, LLMTestResult


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    """Админка для шаблонов промптов"""
    list_display = ['name', 'prompt_type', 'is_active', 'created_at']
    list_filter = ['prompt_type', 'is_active', 'created_at']
    search_fields = ['name', 'slug', 'description']
    readonly_fields = ['created_at', 'updated_at', 'get_variables_display']

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'slug', 'prompt_type', 'description')
        }),
        ('Шаблон', {
            'fields': ('template',)
        }),
        ('Настройки', {
            'fields': ('is_active',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at', 'get_variables_display'),
            'classes': ('collapse',)
        }),
    )

    def get_variables_display(self, obj):
        """Отображает переменные в шаблоне"""
        variables = obj.get_variables()
        if variables:
            return ', '.join(variables)
        return 'Нет переменных'
    get_variables_display.short_description = 'Переменные в шаблоне'


@admin.register(PromptPreset)
class PromptPresetAdmin(admin.ModelAdmin):
    """Админка для пресетов промптов"""
    list_display = ['name', 'prompt', 'is_active', 'created_at']
    list_filter = ['prompt', 'is_active', 'created_at']
    search_fields = ['name', 'prompt__name']
    readonly_fields = ['created_at']


@admin.register(LLMTestResult)
class LLMTestResultAdmin(admin.ModelAdmin):
    """Админка для результатов тестов"""
    list_display = ['id', 'provider', 'model', 'status', 'created_at', 'created_by']
    list_filter = ['provider', 'model', 'status', 'created_at']
    search_fields = ['prompt_text', 'response_text']
    readonly_fields = ['created_at', 'get_cost_display']

    fieldsets = (
        ('Основное', {
            'fields': ('preset', 'provider', 'model', 'status')
        }),
        ('Промпт и ответ', {
            'fields': ('prompt_text', 'response_text')
        }),
        ('Метаданные', {
            'fields': ('usage_info', 'error_message', 'created_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def get_cost_display(self, obj):
        """Отображает стоимость запроса"""
        if obj.usage_info and 'cost_rub' in obj.usage_info:
            return f"{obj.usage_info['cost_rub']} руб."
        return 'Нет данных'
    get_cost_display.short_description = 'Стоимость'
