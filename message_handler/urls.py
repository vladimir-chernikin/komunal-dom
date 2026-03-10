#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
URL маршруты для message_handler app
"""

from django.urls import path
from . import views

app_name = 'message_handler'

urlpatterns = [
    # Web Chat (с трассировкой и _tras_diag_*.md)
    path('', views.web_chat, name='web_chat'),  # ИСПРАВЛЕНО (2026-03-05): Основной WebChat

    # API endpoints
    path('api/send/', views.send_message, name='send_message'),
    path('api/external/', views.send_message_external, name='send_message_external'),  # ИСПРАВЛЕНО (2026-02-24)
    path('api/history/', views.get_chat_history, name='get_chat_history'),
    path('api/dialogs-list/', views.get_dialogs_list, name='get_dialogs_list'),
    path('api/performance-report/', views.get_performance_report, name='get_performance_report'),  # ИСПРАВЛЕНО (2026-03-04)
]
