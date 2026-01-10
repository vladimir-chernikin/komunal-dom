#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Django views для веб-интерфейса AI-чата
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count
import json
import logging

logger = logging.getLogger(__name__)


@login_required
def chat_interface(request):
    """
    Страница с веб-интерфейсом чата

    Args:
        request: Django request

    Returns:
        HttpResponse: Рендеринг шаблона чата
    """
    # Получаем session_id для пользователя
    session_id = f"web_{request.user.id}_{request.session.session_key}"

    context = {
        'user': request.user,
        'session_id': session_id,
    }

    return render(request, 'message_handler/chat.html', context)


@require_http_methods(["POST"])
@csrf_exempt  # Для AJAX запросов будем использовать CSRF token в headers
@login_required
def send_message(request):
    """
    API endpoint для отправки сообщения в чат

    Args:
        request: Django POST request с JSON body:
            {
                "message": "текст сообщения",
                "session_id": "id сессии"
            }

    Returns:
        JsonResponse: {
            "status": "success" | "error",
            "response": "текст ответа бота",
            "service_detected": id_услуги или null
        }
    """
    try:
        # Парсим JSON из request body
        data = json.loads(request.body)
        message_text = data.get('message', '').strip()
        session_id = data.get('session_id', f"web_{request.user.id}")

        if not message_text:
            return JsonResponse({
                'status': 'error',
                'error': 'Пустое сообщение'
            }, status=400)

        # Импортируем MessageHandlerService и MainAgent
        from message_handler_service import MessageHandlerService
        from main_agent import MainAgent

        # Инициализируем сервисы (можно оптимизировать через singleton)
        main_agent = MainAgent()
        message_handler = MessageHandlerService(main_agent=main_agent)

        # Обрабатываем сообщение через MessageHandlerService
        import asyncio

        # Запускаем асинхронную обработку
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                message_handler.handle_incoming_message(
                    text=message_text,
                    user_id=str(request.user.id),
                    channel='web',
                    session_id=session_id,
                    django_user_id=request.user.id
                )
            )
        finally:
            loop.close()

        # Формируем ответ для клиента
        response_data = {
            'status': result.get('status', 'error'),
            'response': result.get('response', ''),
            'service_detected': result.get('service_detected')
        }

        return JsonResponse(response_data)

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        return JsonResponse({
            'status': 'error',
            'error': 'Неверный формат JSON'
        }, status=400)

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Внутренняя ошибка сервера'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_chat_history(request):
    """
    API endpoint для получения истории чата

    Args:
        request: Django GET request с параметром session_id

    Returns:
        JsonResponse: История сообщений сессии
    """
    try:
        from message_handler_service import MessageHandlerService
        import asyncio

        session_id = request.GET.get('session_id', f"web_{request.user.id}")
        limit = int(request.GET.get('limit', 50))

        # Инициализируем MessageHandlerService (без MainAgent для этой функции)
        message_handler = MessageHandlerService()

        # Получаем историю асинхронно
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            messages = loop.run_until_complete(
                message_handler.get_session_messages(session_id, limit)
            )
        finally:
            loop.close()

        return JsonResponse({
            'status': 'success',
            'messages': messages
        })

    except Exception as e:
        logger.error(f"Ошибка получения истории: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_dialogs_list(request):
    """
    API endpoint для получения списка всех диалогов пользователя

    Args:
        request: Django GET request

    Returns:
        JsonResponse: Список диалогов с датой, временем и третьим сообщением
    """
    try:
        from message_handler.models import MessageLog
        from django.db.models import Min, Max

        # ИСПРАВЛЕНО (2026-01-10): django_user → django_user_id (IntegerField)
        # ИСПРАВЛЕНО (2026-01-10): Добавлен фильтр django_user_id__isnull=False
        # ИСПРАВЛЕНО (2026-01-10): created_at → timestamp (правильное имя поля в модели)
        sessions = MessageLog.objects.filter(
            channel='web',
            django_user_id=request.user.id,
            django_user_id__isnull=False
        ).values('session_id').annotate(
            first_message_time=Min('timestamp'),
            last_message_time=Max('timestamp'),
            message_count=Count('message_id')
        ).order_by('-last_message_time')

        dialogs_list = []

        for session in sessions:
            session_id = session['session_id']

            # ИСПРАВЛЕНО (2026-01-10): django_user → django_user_id
            # ИСПРАВЛЕНО (2026-01-10): created_at → timestamp (правильное имя поля в модели)
            # Получаем третье сообщение (или первое, если сообщений меньше)
            messages = MessageLog.objects.filter(
                channel='web',
                django_user_id=request.user.id,
                session_id=session_id
            ).order_by('timestamp')

            third_message_text = ""
            if messages.count() >= 3:
                # ИСПРАВЛЕНО (2026-01-10): text → message_content (правильное имя поля в модели)
                third_message_text = messages[2].message_content[:100]  # Первые 100 символов
            elif messages.count() > 0:
                # ИСПРАВЛЕНО (2026-01-10): text → message_content (правильное имя поля в модели)
                third_message_text = messages[0].message_content[:100]

            dialogs_list.append({
                'session_id': session_id,
                'date': session['first_message_time'].strftime('%Y-%m-%d'),
                'time': session['first_message_time'].strftime('%H:%M'),
                'preview': third_message_text,
                'message_count': session['message_count']
            })

        return JsonResponse({
            'status': 'success',
            'dialogs': dialogs_list
        })

    except Exception as e:
        logger.error(f"Ошибка получения списка диалогов: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)
