#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
URL конфигурация для LLM Tester
"""

from django.urls import path
from . import views

app_name = 'llm_tester'

urlpatterns = [
    # Дашборд
    path('', views.llm_tester_dashboard, name='dashboard'),

    # База промптов (все версии)
    path('prompts/', views.prompt_list, name='prompt_list'),

    # Тестирование промпта
    path('test/<int:template_id>/', views.test_prompt, name='test_prompt'),

    # Отправка запроса в LLM
    path('api/send-request/', views.send_llm_request, name='send_request'),

    # Обновление шаблона
    path('api/update-template/', views.update_template, name='update_template'),

    # Загрузка версии шаблона
    path('api/load-version/<int:template_id>/', views.load_template_version, name='load_template_version'),

    # Сохранение пресета
    path('api/save-preset/', views.save_preset, name='save_preset'),

    # Загрузка пресета
    path('api/load-preset/', views.load_preset, name='load_preset'),

    # Результаты тестов
    path('results/', views.test_results, name='test_results'),
]
