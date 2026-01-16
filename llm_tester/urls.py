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

    # Тестирование промпта
    path('test/<int:template_id>/', views.test_prompt, name='test_prompt'),

    # Отправка запроса в LLM
    path('api/send-request/', views.send_llm_request, name='send_request'),

    # Сохранение пресета
    path('api/save-preset/', views.save_preset, name='save_preset'),

    # Загрузка пресета
    path('api/load-preset/', views.load_preset, name='load_preset'),

    # Результаты тестов
    path('results/', views.test_results, name='test_results'),
]
