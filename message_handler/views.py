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


# ИСПРАВЛЕНО (2026-02-24): Добавлен внешний API для интеграций
from django.conf import settings
from django.http import HttpResponseForbidden

# API токены для внешних интеграций (можно вынести в БД или settings)
API_TOKENS = getattr(settings, 'EXTERNAL_API_TOKENS', {
    'v1979v': 'asterisk_integration',  # Основной токен для Asterisk
    'dev_test_token_2024': 'dev_system',
})

# IP whitelist (опционально)
ALLOWED_IPS = getattr(settings, 'EXTERNAL_API_ALLOWED_IPS', [])


@require_http_methods(["POST"])
@csrf_exempt
def send_message_external(request):
    """
    API endpoint для внешних систем (Asterisk, CRM, мобильные приложения и т.д.)

    Аутентификация:
        - API token в JSON body (поле "token")
        - Опционально: IP whitelist

    Headers:
        Content-Type: application/json

    Body:
    {
        "token": "v1979v",
        "message": "текст сообщения",
        "session_id": "api_client_123",
        "user_id": "external_user_456"
    }

    Response:
    {
        "status": "success" | "error",
        "response": "текст ответа бота",
        "service_detected": id_услуги или null,
        "session_id": "api_client_123"
    }

    Пример использования:
    curl -X POST http://komunal-dom.ru/chat/api/external/ \\
      -H "Content-Type: application/json" \\
      -d '{"token": "v1979v", "message": "У меня течет труба", "session_id": "test_123"}'
    """
    # Проверка IP whitelist (если настроен)
    if ALLOWED_IPS:
        client_ip = get_client_ip(request)
        if client_ip not in ALLOWED_IPS:
            logger.warning(f"Попытка доступа с запрещенного IP: {client_ip}")
            return JsonResponse({
                'status': 'error',
                'error': 'Forbidden - IP not allowed'
            }, status=403)

    try:
        # Парсим JSON из request body
        data = json.loads(request.body)

        # Проверка API токена в JSON body
        token = data.get('token')
        if not token:
            return JsonResponse({
                'status': 'error',
                'error': 'Unauthorized - Missing token'
            }, status=401)

        if token not in API_TOKENS:
            logger.warning(f"Попытка доступа с неверным токеном: {token[:10]}...")
            return JsonResponse({
                'status': 'error',
                'error': 'Unauthorized - Invalid token'
            }, status=401)

        # Токен валиден
        client_system = API_TOKENS[token]
        logger.info(f"[EXTERNAL API] Запрос от {client_system} (token: {token[:10]}...)")

        message_text = data.get('message', '').strip()
        session_id = data.get('session_id')
        user_id = data.get('user_id', f'external_{client_system}_user')

        if not message_text:
            return JsonResponse({
                'status': 'error',
                'error': 'Empty message'
            }, status=400)

        if not session_id:
            return JsonResponse({
                'status': 'error',
                'error': 'Missing session_id'
            }, status=400)

        # Импортируем сервисы
        from message_handler_service import MessageHandlerService
        from main_agent import MainAgent

        # Инициализируем сервисы
        main_agent = MainAgent()
        message_handler = MessageHandlerService(main_agent=main_agent)

        # Обрабатываем сообщение через MessageHandlerService
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                message_handler.handle_incoming_message(
                    text=message_text,
                    user_id=user_id,
                    channel='api',  # НОВЫЙ канал для внешних систем
                    session_id=session_id,
                    django_user_id=None  # Внешние системы без Django auth
                )
            )
        finally:
            loop.close()

        # Формируем ответ для клиента
        response_data = {
            'status': result.get('status', 'error'),
            'response': result.get('response', ''),
            'service_detected': result.get('service_detected'),
            'session_id': session_id
        }

        logger.info(f"[EXTERNAL API] Ответ: {response_data['status']}")
        return JsonResponse(response_data)

    except json.JSONDecodeError as e:
        logger.error(f"[EXTERNAL API] Ошибка парсинга JSON: {e}")
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid JSON format'
        }, status=400)

    except Exception as e:
        logger.error(f"[EXTERNAL API] Ошибка обработки: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': 'Internal server error'
        }, status=500)


def get_client_ip(request):
    """Получает реальный IP клиента с учётом X-Forwarded-For"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
