#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
URL маршруты для message_handler app
"""

from django.urls import path
from . import views

app_name = 'message_handler'

urlpatterns = [
    # Веб-интерфейс чата (главная страница /chat/)
    path('', views.chat_interface, name='chat_interface'),

    # API endpoints
    path('api/send/', views.send_message, name='send_message'),
    path('api/history/', views.get_chat_history, name='get_chat_history'),
]
