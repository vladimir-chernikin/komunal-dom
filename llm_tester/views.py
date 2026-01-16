#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Views для LLM Tester - приложения для тестирования промптов
"""

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from asgiref.sync import async_to_sync
from django.core.paginator import Paginator

from .models import PromptTemplate, PromptPreset, LLMTestResult

logger = logging.getLogger(__name__)


@login_required
def llm_tester_dashboard(request):
    """
    Дашборд для тестирования LLM промптов
    """
    # Получаем все активные шаблоны
    templates = PromptTemplate.objects.filter(is_active=True).order_by('prompt_type', 'name')

    # Получаем последние результаты тестов
    recent_results = LLMTestResult.objects.all().select_related('preset', 'created_by')[:20]

    context = {
        'templates': templates,
        'recent_results': recent_results,
        'title': 'LLM Tester - Тестирование промптов',
    }
    return render(request, 'llm_tester/dashboard.html', context)


@login_required
def test_prompt(request, template_id):
    """
    Страница тестирования конкретного промпта
    """
    template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)

    # Получаем пресеты для этого шаблона
    presets = template.presets.filter(is_active=True)

    # Получаем переменные из шаблона
    variables = template.get_variables()

    context = {
        'template': template,
        'presets': presets,
        'variables': variables,
        'title': f'Тестирование: {template.name}',
        'models': {
            'yandexgpt': [
                {'value': 'lite', 'label': 'YandexGPT Lite'},
                {'value': 'pro', 'label': 'YandexGPT Pro'},
            ],
            'gigachat': [
                {'value': 'GigaChat', 'label': 'GigaChat'},
                {'value': 'GigaChat-2', 'label': 'GigaChat-2'},
                {'value': 'GigaChat-Plus', 'label': 'GigaChat-Plus'},
                {'value': 'GigaChat-2.1', 'label': 'GigaChat-2.1'},
            ],
        },
    }
    return render(request, 'llm_tester/test_prompt.html', context)


@require_http_methods(["POST"])
@login_required
def send_llm_request(request):
    """
    Отправка запроса в LLM
    """
    try:
        # Получаем данные из запроса
        data = json.loads(request.body)
        template_id = data.get('template_id')
        provider = data.get('provider', 'yandexgpt')
        model = data.get('model', 'lite')
        variables = data.get('variables', {})

        # Получаем шаблон
        template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)

        # Подставляем переменные в шаблон
        try:
            prompt_text = template.template.format(**variables)
        except KeyError as e:
            return JsonResponse({
                'status': 'error',
                'error': f'Отсутствует переменная: {e}'
            }, status=400)

        # Импортируем AIAgentService
        from ai_agent_service import AIAgentService

        # Создаем сервис и отправляем запрос
        ai_service = AIAgentService(provider=provider)

        # Используем async_to_sync для вызова async метода
        response, usage_info = async_to_sync(ai_service.call_llm)(
            prompt=prompt_text,
            provider=provider,
            model=model
        )

        # Сохраняем результат
        result = LLMTestResult.objects.create(
            provider=provider,
            model=model,
            prompt_text=prompt_text,
            response_text=response,
            usage_info=usage_info,
            status='success',
            created_by=request.user
        )

        logger.info(
            f"LLM Tester: запрос отправлен успешно. "
            f"Провайдер: {provider}, Модель: {model}, "
            f"Стоимость: {usage_info.get('cost_rub', 0)} руб."
        )

        return JsonResponse({
            'status': 'success',
            'result_id': result.id,
            'response': response,
            'usage_info': usage_info,
            'prompt_text': prompt_text,
        })

    except Exception as e:
        logger.error(f"LLM Tester ошибка: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@login_required
def save_preset(request):
    """
    Сохранение пресета промпта
    """
    try:
        data = json.loads(request.body)
        template_id = data.get('template_id')
        name = data.get('name')
        variables = data.get('variables', {})

        if not name:
            return JsonResponse({
                'status': 'error',
                'error': 'Название пресета обязательно'
            }, status=400)

        template = get_object_or_404(PromptTemplate, id=template_id, is_active=True)

        # Создаем пресет
        preset = PromptPreset.objects.create(
            prompt=template,
            name=name,
            variable_values=variables
        )

        logger.info(f"LLM Tester: создан пресет '{name}' для шаблона '{template.name}'")

        return JsonResponse({
            'status': 'success',
            'preset_id': preset.id,
            'name': preset.name
        })

    except Exception as e:
        logger.error(f"LLM Tester ошибка сохранения пресета: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
@login_required
def load_preset(request):
    """
    Загрузка значений переменных из пресета
    """
    try:
        data = json.loads(request.body)
        preset_id = data.get('preset_id')

        preset = get_object_or_404(PromptPreset, id=preset_id, is_active=True)

        return JsonResponse({
            'status': 'success',
            'variables': preset.variable_values,
            'preset_name': preset.name
        })

    except Exception as e:
        logger.error(f"LLM Tester ошибка загрузки пресета: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@login_required
def test_results(request):
    """
    Страница со списком всех результатов тестов
    """
    # Получаем все результаты
    results = LLMTestResult.objects.all().select_related('preset', 'created_by')

    # Фильтрация
    provider_filter = request.GET.get('provider')
    model_filter = request.GET.get('model')
    status_filter = request.GET.get('status')

    if provider_filter:
        results = results.filter(provider=provider_filter)
    if model_filter:
        results = results.filter(model=model_filter)
    if status_filter:
        results = results.filter(status=status_filter)

    # Пагинация
    paginator = Paginator(results, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'title': 'Результаты тестов LLM',
        'provider_filter': provider_filter,
        'model_filter': model_filter,
        'status_filter': status_filter,
    }
    return render(request, 'llm_tester/test_results.html', context)
