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
import uuid
import os

logger = logging.getLogger(__name__)


@login_required
def web_chat(request):
    """
    Web Chat страница с трассировкой (_tras_diag_*.md)

    ИСПОЛЬЗОВАНИЕ (2026-03-05):
    - Основной WebChat для создания заявок
    - Использует MainAgent (как Telegram и API)
    - Генерирует отчеты трассировки в /tmp/_tras_diag_*.md
    - Канал: 'web'

    URL: /chat/
    """
    from portal.models import UserProfile

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    context = {
        'user_profile': profile,
        'user': request.user,
    }
    return render(request, 'message_handler/web_chat.html', context)


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

        # ИСПРАВЛЕНО (2026-03-05): Генерируем отчет трассировки для WebChat
        trace_file = None
        try:
            from trace_report_service import TraceReportService
            import os

            # Создаем новый event loop для генерации отчета
            trace_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(trace_loop)

            try:
                # Генерируем отчет
                trace_file = trace_loop.run_until_complete(
                    TraceReportService.generate_trace_report(session_id)
                )
            finally:
                trace_loop.close()

            # Устанавливаем права 644 для веб-доступа
            if trace_file and os.path.exists(trace_file):
                os.chmod(trace_file, 0o644)
                logger.info(f"[WEB_CHAT] Сгенерирован отчет трассировки: {trace_file}")

        except Exception as trace_error:
            logger.warning(f"[WEB_CHAT] Не удалось сгенерировать отчет трассировки: {trace_error}")
            # Не прерываем работу, если отчет не создался

        # Формируем ответ для клиента
        response_data = {
            'status': result.get('status', 'error'),
            'response': result.get('response', ''),
            'service_detected': result.get('service_detected'),
            'trace_file': os.path.basename(trace_file) if trace_file else None  # ИСПРАВЛЕНО (2026-03-05)
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


def log_api_error(error_type, status_code, error_message, error_details=None,
                  session_id=None, request_id=None, client_ip=None, client_system=None,
                  token_preview=None, request_data=None, message_preview=None,
                  user_id=None, nomer=None):
    """
    Логирование ошибок API в модель APIErrorLog

    ИСПОЛЬЗОВАНИЕ (2026-03-05):
    - Вызов из send_message_external при любых ошибках
    - Сохранение полной информации о запросе для дебага

    Args:
        error_type: Тип ошибки (auth, validation, processing, timeout, internal)
        status_code: HTTP статус код
        error_message: Краткое описание ошибки
        error_details: Детали ошибки (traceback)
        session_id: ID сессии
        request_id: Уникальный ID запроса
        client_ip: IP клиента
        client_system: Клиентская система
        token_preview: Первые символы токена
        request_data: JSON тело запроса
        message_preview: Первые символы сообщения
        user_id: User ID
        nomer: NOMER (абонент)
    """
    from message_handler.models import APIErrorLog

    try:
        # Генерируем request_id если не передан
        if not request_id:
            request_id = str(uuid.uuid4())[:8]

        APIErrorLog.objects.create(
            error_type=error_type,
            status_code=status_code,
            error_message=error_message[:500],  # Обрезаем до 500 символов
            error_details=error_details[:2000] if error_details else None,  # Обрезаем до 2000 символов
            session_id=session_id[:255] if session_id else None,
            request_id=request_id,
            client_ip=client_ip,
            client_system=client_system[:100] if client_system else None,
            token_preview=token_preview[:20] if token_preview else '',
            request_data=request_data,
            message_preview=message_preview[:200] if message_preview else '',
            user_id=user_id[:100] if user_id else None,
            nomer=nomer[:20] if nomer else None,
        )
        logger.info(f"[API ERROR] Logged: {error_type} | {status_code} | {request_id}")
    except Exception as e:
        logger.error(f"[API ERROR] Failed to log error: {e}", exc_info=True)





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
    # ИСПРАВЛЕНО (2026-03-05): Генерируем request_id для трассировки
    request_id = str(uuid.uuid4())[:8]
    client_ip = get_client_ip(request)

    # ИСПРАВЛЕНО (2026-03-05): Инициализируем переменные для логирования
    token = None
    client_system = None
    data = {}
    session_id = None
    user_id = None
    nomer = None
    message_text = None

    # Проверка IP whitelist (если настроен)
    if ALLOWED_IPS:
        if client_ip not in ALLOWED_IPS:
            logger.warning(f"Попытка доступа с запрещенного IP: {client_ip}")
            # Логируем ошибку
            try:
                request_data = json.loads(request.body)
            except:
                request_data = {}

            log_api_error(
                error_type='auth',
                status_code=403,
                error_message='Forbidden - IP not allowed',
                error_details=f'IP {client_ip} not in whitelist',
                request_id=request_id,
                client_ip=client_ip,
                request_data=request_data
            )
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
            # Логируем ошибку отсутствия токена
            log_api_error(
                error_type='auth',
                status_code=401,
                error_message='Unauthorized - Missing token',
                error_details='Token field is missing in request body',
                request_id=request_id,
                client_ip=client_ip,
                request_data=data
            )
            return JsonResponse({
                'status': 'error',
                'error': 'Unauthorized - Missing token'
            }, status=401)

        if token not in API_TOKENS:
            logger.warning(f"Попытка доступа с неверным токеном: {token[:10]}...")
            # Логируем ошибку неверного токена
            log_api_error(
                error_type='auth',
                status_code=401,
                error_message='Unauthorized - Invalid token',
                error_details=f'Token {token[:20]} not found in API_TOKENS',
                request_id=request_id,
                client_ip=client_ip,
                token_preview=token[:20],
                request_data=data
            )
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
        nomer = data.get('nomer')  # ИСПРАВЛЕНО (2026-03-05): Параметр NOMER для идентификации абонента

        if not message_text:
            # Логируем ошибку пустого сообщения
            log_api_error(
                error_type='validation',
                status_code=400,
                error_message='Empty message',
                error_details='Message field is empty or missing',
                request_id=request_id,
                client_ip=client_ip,
                client_system=client_system,
                token_preview=token[:20],
                request_data=data,
                user_id=user_id,
                nomer=nomer
            )
            return JsonResponse({
                'status': 'error',
                'error': 'Empty message'
            }, status=400)

        if not session_id:
            # Логируем ошибку отсутствующего session_id
            log_api_error(
                error_type='validation',
                status_code=400,
                error_message='Missing session_id',
                error_details='session_id field is missing in request body',
                request_id=request_id,
                client_ip=client_ip,
                client_system=client_system,
                token_preview=token[:20],
                request_data=data,
                user_id=user_id,
                nomer=nomer,
                message_preview=message_text[:200]
            )
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

        # ИСПРАВЛЕНО (2026-03-05): Формируем metadata с информацией об API вызове
        api_metadata = {
            'client_system': client_system  # УБРАЛИ 'channel' - он добавляется в MessageHandlerService
        }
        if nomer:
            api_metadata['api_info'] = {'nomer': nomer}
            logger.info(f"[EXTERNAL API] Передан NOMER: {nomer}")
        logger.info(f"[EXTERNAL API] api_metadata: {api_metadata}")

        loop_closed = False
        try:
            result = loop.run_until_complete(
                message_handler.handle_incoming_message(
                    text=message_text,
                    user_id=user_id,
                    channel='api',  # НОВЫЙ канал для внешних систем
                    session_id=session_id,
                    django_user_id=None,  # Внешние системы без Django auth
                    metadata=api_metadata  # Передаем metadata с NOMER
                )
            )
        except Exception as processing_error:
            # Логируем ошибку обработки сообщения
            import traceback
            error_details = traceback.format_exc()
            log_api_error(
                error_type='processing',
                status_code=500,
                error_message=f'Error processing message: {str(processing_error)[:200]}',
                error_details=error_details[:2000],
                request_id=request_id,
                client_ip=client_ip,
                client_system=client_system,
                token_preview=token[:20] if token else None,
                request_data=data,
                user_id=user_id,
                nomer=nomer,
                message_preview=message_text[:200] if message_text else None,
                session_id=session_id
            )
            loop.close()
            loop_closed = True
            raise  # Перебрасываем исключение для обработки в основном except
        finally:
            if not loop_closed:
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
        # Логируем ошибку парсинга JSON
        log_api_error(
            error_type='validation',
            status_code=400,
            error_message='Invalid JSON format',
            error_details=str(e),
            request_id=request_id,
            client_ip=client_ip,
            request_data={'raw_body': str(request.body)[:500]}
        )
        return JsonResponse({
            'status': 'error',
            'error': 'Invalid JSON format'
        }, status=400)

    except Exception as e:
        logger.error(f"[EXTERNAL API] Ошибка обработки: {e}", exc_info=True)
        # Логируем общую внутреннюю ошибку (если ещё не залогировали)
        import traceback
        error_details = traceback.format_exc()
        log_api_error(
            error_type='internal',
            status_code=500,
            error_message=f'Internal server error: {str(e)[:200]}',
            error_details=error_details[:2000],
            request_id=request_id,
            client_ip=client_ip
        )
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


@require_http_methods(["GET"])
@csrf_exempt  # ИСПРАВЛЕНО (2026-03-04): Убран @login_required для тестирования через API
def get_performance_report(request):
    """
    API endpoint для получения отчета производительности (карта отработки запроса)

    Args:
        request: Django GET request с параметром session_id

    Returns:
        JsonResponse: HTML отчет или ошибка
    """
    try:
        from performance_report_service import PerformanceReportService
        from message_handler.models import MessageLog

        session_id = request.GET.get('session_id')
        if not session_id:
            return JsonResponse({
                'status': 'error',
                'error': 'Missing session_id parameter'
            }, status=400)

        # Загружаем performance данные из metadata последнего сообщения
        messages = MessageLog.objects.filter(
            session_id=session_id
        ).order_by('-timestamp')[:10]

        performance_data = None
        for msg in messages:
            if msg.metadata and isinstance(msg.metadata, dict):
                if 'performance' in msg.metadata:
                    performance_data = msg.metadata['performance']
                    break

        if performance_data:
            # Генерируем HTML отчет
            html = PerformanceReportService.generate_html_report(performance_data)

            return JsonResponse({
                'status': 'success',
                'html': html
            })
        else:
            # Данные производительности не найдены
            html = PerformanceReportService.generate_from_session_id(session_id)

            return JsonResponse({
                'status': 'success',
                'html': html,
                'message': 'Performance data not available for this session'
            })

    except Exception as e:
        logger.error(f"Ошибка генерации performance отчета: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)
