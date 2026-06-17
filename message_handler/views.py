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
import time

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

        # Импортируем новый единый обработчик заявок
        from message_handler_service import MessageHandlerService

        message_handler = MessageHandlerService()

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
            'trace_file': os.path.basename(trace_file) if trace_file else None,  # ИСПРАВЛЕНО (2026-03-05)
            'close_session': result.get('close_session', False),
            'finish_reason': result.get('finish_reason'),
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
    request_start_perf = time.perf_counter()
    client_ip = get_client_ip(request)
    logger.warning(f"[PERF API] request_id={request_id} phase=request_start ip={client_ip}")

    # ИСПРАВЛЕНО (2026-03-05): Инициализируем переменные для логирования
    token = None
    client_system = None
    data = {}
    session_id = None
    user_id = None
    nomer = None
    message_text = None
    VOICE_SCHEMA_V2 = 'asterisk_voice_v2'
    VOICE_SCHEMA_V21 = 'asterisk_voice_v2.1'
    VOICE_SUPPORTED_SCHEMAS = {VOICE_SCHEMA_V2, VOICE_SCHEMA_V21}
    VOICE_V21_EVENTS = {'user_message', 'call_ended'}
    VOICE_CALL_END_REASONS = {'caller_hangup', 'normal', 'timeout', 'unknown'}

    def _voice_schema(payload):
        return payload.get('schema_version') if isinstance(payload, dict) else None

    def _is_voice_payload(payload):
        return isinstance(payload, dict) and _voice_schema(payload) in VOICE_SUPPORTED_SCHEMAS

    def _as_positive_int(value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    def _voice_v21_turn(payload):
        turn = payload.get('turn') if isinstance(payload, dict) else {}
        if not isinstance(turn, dict):
            return None
        revision = _as_positive_int(turn.get('revision'))
        if not turn.get('turn_id') or revision is None:
            return None
        return {
            'turn_id': str(turn.get('turn_id')).strip(),
            'revision': revision,
        }

    def _voice_v2_error(message, status_code=400, payload=None):
        payload = payload if isinstance(payload, dict) else data
        if _voice_schema(payload) == VOICE_SCHEMA_V21:
            return JsonResponse({
                'status': 'error',
                'schema_version': VOICE_SCHEMA_V21,
                'turn': _voice_v21_turn(payload),
                'response': message,
                'close_session': True,
            }, status=status_code)
        return JsonResponse({
            'status': 'error',
            'response': message,
            'session_id': (payload.get('session_id') if isinstance(payload, dict) else None) or '',
            'service_detected': None,
            'close_session': True,
        }, status=status_code)

    def _validate_voice_payload(payload):
        schema_version = _voice_schema(payload)
        if schema_version == VOICE_SCHEMA_V2:
            required_top = ('schema_version', 'source', 'channel', 'token', 'session_id', 'user_id', 'message')
        else:
            required_top = ('schema_version', 'event', 'source', 'channel', 'token', 'session_id', 'user_id')
        missing = [
            field for field in required_top
            if not str(payload.get(field) or '').strip()
        ]
        call = payload.get('call')
        if not isinstance(call, dict):
            missing.append('call')
        else:
            required_call = ('direction', 'client_phone', 'company_phone')
            missing.extend(
                f'call.{field}' for field in required_call
                if not str(call.get(field) or '').strip()
            )
        if missing:
            return 'Missing required field(s): ' + ', '.join(missing)
        if payload.get('source') != 'asterisk':
            return 'Invalid source: expected asterisk'
        if payload.get('channel') != 'voice':
            return 'Invalid channel: expected voice'
        if call.get('direction') not in {'inbound', 'outbound'}:
            return 'Invalid call.direction: expected inbound or outbound'
        if schema_version == VOICE_SCHEMA_V21:
            event = payload.get('event')
            if event not in VOICE_V21_EVENTS:
                return 'Invalid event: expected user_message or call_ended'
            if event == 'user_message':
                if not str(payload.get('message') or '').strip():
                    return 'Missing required field(s): message'
                turn = payload.get('turn')
                if not isinstance(turn, dict):
                    return 'Missing required field(s): turn'
                turn_id = str(turn.get('turn_id') or '').strip()
                revision = _as_positive_int(turn.get('revision'))
                if not turn_id:
                    return 'Missing required field(s): turn.turn_id'
                if revision is None:
                    return 'Invalid turn.revision: expected positive integer'
                supersedes_revision = turn.get('supersedes_revision')
                if supersedes_revision not in (None, ''):
                    supersedes_revision = _as_positive_int(supersedes_revision)
                    if supersedes_revision is None:
                        return 'Invalid turn.supersedes_revision: expected positive integer or null'
                    if supersedes_revision >= revision:
                        return 'Invalid turn.supersedes_revision: must be lower than revision'
            if event == 'call_ended':
                reason = str(payload.get('reason') or 'unknown').strip() or 'unknown'
                if reason not in VOICE_CALL_END_REASONS:
                    return 'Invalid reason: expected caller_hangup, normal, timeout or unknown'
        return None

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
            return _voice_v2_error('Forbidden - IP not allowed', 403, request_data)

    try:
        # Парсим JSON из request body
        data = json.loads(request.body)
        is_voice_payload = _is_voice_payload(data)
        schema_version = _voice_schema(data)
        if not is_voice_payload:
            log_api_error(
                error_type='validation',
                status_code=400,
                error_message='Unsupported external API schema_version',
                error_details='Expected schema_version=asterisk_voice_v2 or asterisk_voice_v2.1',
                request_id=request_id,
                client_ip=client_ip,
                request_data=data
            )
            return _voice_v2_error('Unsupported schema_version: expected asterisk_voice_v2 or asterisk_voice_v2.1', 400, data)

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
            return _voice_v2_error('Unauthorized - Missing token', 401, data)

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
            return _voice_v2_error('Unauthorized - Invalid token', 401, data)

        # Токен валиден
        client_system = API_TOKENS[token]
        logger.info(f"[EXTERNAL API] Запрос от {client_system} (token: {token[:10]}...)")

        validation_error = _validate_voice_payload(data)
        if validation_error:
            log_api_error(
                error_type='validation',
                status_code=400,
                error_message='Invalid asterisk voice payload',
                error_details=validation_error,
                request_id=request_id,
                client_ip=client_ip,
                client_system=client_system,
                token_preview=token[:20],
                request_data=data
            )
            return _voice_v2_error(validation_error, 400, data)
        call_data = data.get('call') or {}
        event = data.get('event') if schema_version == VOICE_SCHEMA_V21 else 'user_message'
        message_text = str(data.get('message') or '').strip()
        session_id = str(data.get('session_id') or '').strip()
        user_id = str(data.get('user_id') or '').strip()
        nomer = str(call_data.get('client_phone') or '').strip()

        if schema_version == VOICE_SCHEMA_V21 and event == 'call_ended':
            from message_handler.voice_revision_guard import mark_voice_call_ended

            end_result = mark_voice_call_ended(
                session_id=session_id,
                user_id=user_id,
                reason=str(data.get('reason') or 'unknown').strip() or 'unknown',
                call=call_data,
                schema_version=VOICE_SCHEMA_V21,
            )
            logger.info(
                f"[EXTERNAL API] asterisk_voice_v2.1 call_ended "
                f"session={session_id} reason={end_result.get('end_reason')}"
            )
            return JsonResponse({
                'status': 'success',
                'schema_version': VOICE_SCHEMA_V21,
                'turn': None,
                'response': '',
                'close_session': True,
            })

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
            return _voice_v2_error('Empty message', 400, data)

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
            return _voice_v2_error('Missing session_id', 400, data)

        turn_data = {}
        revision_guard_result = None
        if schema_version == VOICE_SCHEMA_V21:
            from message_handler.voice_revision_guard import register_voice_turn_revision

            raw_turn = data.get('turn') or {}
            revision = _as_positive_int(raw_turn.get('revision'))
            supersedes_revision = _as_positive_int(raw_turn.get('supersedes_revision'))
            turn_data = {
                'turn_id': str(raw_turn.get('turn_id') or '').strip(),
                'revision': revision,
                'supersedes_revision': supersedes_revision,
            }
            revision_guard_result = register_voice_turn_revision(
                session_id=session_id,
                turn_id=turn_data['turn_id'],
                revision=revision,
                supersedes_revision=supersedes_revision,
                user_id=user_id,
                message=message_text,
                call=call_data,
                schema_version=VOICE_SCHEMA_V21,
            )
            if not revision_guard_result.get('is_current'):
                logger.info(
                    f"[EXTERNAL API] asterisk_voice_v2.1 stale revision skipped "
                    f"session={session_id} turn={turn_data['turn_id']} "
                    f"revision={revision} latest={revision_guard_result.get('latest_revision')}"
                )
                return JsonResponse({
                    'status': 'success',
                    'schema_version': VOICE_SCHEMA_V21,
                    'turn': {
                        'turn_id': turn_data['turn_id'],
                        'revision': revision,
                    },
                    'response': '',
                    'close_session': bool(revision_guard_result.get('session_ended')),
                })

        validated_ms = (time.perf_counter() - request_start_perf) * 1000
        logger.warning(
            f"[PERF API] request_id={request_id} phase=validated "
            f"elapsed_ms={validated_ms:.1f} session={session_id} "
            f"user={user_id} message_chars={len(message_text)}"
        )

        # Импортируем сервисы
        from message_handler_service import MessageHandlerService
        message_handler = MessageHandlerService()

        # Обрабатываем сообщение через MessageHandlerService
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # ИСПРАВЛЕНО (2026-03-05): Формируем metadata с информацией об API вызове
        api_metadata = {
            'client_system': client_system  # УБРАЛИ 'channel' - он добавляется в MessageHandlerService
        }
        api_metadata.update({
            'schema_version': schema_version,
            'source': 'asterisk',
            'external_channel': 'voice',
            'event': event,
            'session_id': session_id,
            'client_phone': nomer,
            'company_phone': str(call_data.get('company_phone') or '').strip(),
            'asterisk_channel_id': str(call_data.get('asterisk_channel_id') or '').strip(),
            'call': {
                'direction': call_data.get('direction'),
                'client_phone': nomer,
                'company_phone': str(call_data.get('company_phone') or '').strip(),
                'asterisk_channel_id': str(call_data.get('asterisk_channel_id') or '').strip(),
            },
            'api_info': {
                'nomer': nomer,
                'client_phone': nomer,
                'company_phone': str(call_data.get('company_phone') or '').strip(),
                'call_direction': call_data.get('direction'),
                'asterisk_channel_id': str(call_data.get('asterisk_channel_id') or '').strip(),
            },
            'customer_identifiers': {
                'telefon': nomer,
            },
        })
        if schema_version == VOICE_SCHEMA_V21:
            api_metadata.update({
                'turn': {
                    'turn_id': turn_data.get('turn_id'),
                    'revision': turn_data.get('revision'),
                    'supersedes_revision': turn_data.get('supersedes_revision'),
                },
                'voice_revision': {
                    'session_id': session_id,
                    'turn_id': turn_data.get('turn_id'),
                    'revision': turn_data.get('revision'),
                    'supersedes_revision': turn_data.get('supersedes_revision'),
                    'latest_revision': (revision_guard_result or {}).get('latest_revision'),
                },
            })
        logger.info(
            f"[EXTERNAL API] {schema_version} direction={call_data.get('direction')} "
            f"client_phone={nomer} company_phone={api_metadata['company_phone']} "
            f"asterisk_channel_id={api_metadata['asterisk_channel_id']}"
        )
        logger.info(f"[EXTERNAL API] api_metadata: {api_metadata}")

        loop_closed = False
        handler_start_perf = time.perf_counter()
        logger.warning(
            f"[PERF API] request_id={request_id} phase=handler_start "
            f"session={session_id}"
        )
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
            handler_ms = (time.perf_counter() - handler_start_perf) * 1000
            logger.warning(
                f"[PERF API] request_id={request_id} phase=handler_done "
                f"duration_ms={handler_ms:.1f} status={result.get('status')} "
                f"service_detected={result.get('service_detected')} "
                f"response_chars={len(result.get('response') or '')}"
            )
        except Exception as processing_error:
            # Логируем ошибку обработки сообщения
            handler_ms = (time.perf_counter() - handler_start_perf) * 1000
            logger.warning(
                f"[PERF API] request_id={request_id} phase=handler_error "
                f"duration_ms={handler_ms:.1f} error={str(processing_error)[:120]}"
            )
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
        if schema_version == VOICE_SCHEMA_V21:
            response_data = {
                'status': result.get('status', 'error'),
                'schema_version': VOICE_SCHEMA_V21,
                'turn': {
                    'turn_id': turn_data.get('turn_id'),
                    'revision': turn_data.get('revision'),
                },
                'response': '' if result.get('superseded_revision') else result.get('response', ''),
                'close_session': False if result.get('superseded_revision') else result.get('close_session', False),
            }
        else:
            response_data = {
                'status': result.get('status', 'error'),
                'response': result.get('response', ''),
                'service_detected': result.get('service_detected'),
                'session_id': session_id,
                'close_session': result.get('close_session', False),
            }

        total_ms = (time.perf_counter() - request_start_perf) * 1000
        performance = result.get('performance') or {}
        timings = performance.get('stages') or []
        stage_summary = ",".join(
            f"{item.get('name')}:{(item.get('duration_ms') or 0):.0f}"
            for item in timings[:8]
            if item.get('duration_ms') is not None
        )
        logger.warning(
            f"[PERF API] request_id={request_id} phase=response_ready "
            f"total_ms={total_ms:.1f} handler_ms={handler_ms:.1f} "
            f"tracer_total_ms={(performance.get('total_duration_ms') or 0):.1f} "
            f"session={session_id} status={response_data['status']} "
            f"service_detected={result.get('service_detected')} "
            f"dialog_finished={result.get('dialog_finished')} "
            f"response_chars={len(response_data['response'])} stages={stage_summary}"
        )
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
        return _voice_v2_error('Invalid JSON format', 400, {})

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
        return _voice_v2_error('Internal server error', 500, data)


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
        def merge_session_performance(items):
            if not items:
                return None
            if len(items) == 1:
                return items[0]['performance']

            merged = {
                'session_id': session_id,
                'stages': [],
                'microservices': [],
                'llm_calls': [],
                'total_duration_ms': 0,
                'microservices_total_ms': 0,
                'llm_total_cost_rub': 0,
                'llm_total_tokens': 0,
            }
            synthetic_start = 0.0
            for item in items:
                perf = item['performance']
                stages = perf.get('stages') or []
                min_start = min(
                    (stage.get('start_time') for stage in stages if stage.get('start_time') is not None),
                    default=0,
                )
                message_prefix = f"{item['direction']}#{item['id']}"
                block_duration = perf.get('total_duration_ms') or 0

                for stage in stages:
                    stage_copy = dict(stage)
                    stage_copy['name'] = f"{message_prefix}.{stage_copy.get('name', 'stage')}"
                    if stage_copy.get('start_time') is not None:
                        relative_ms = (stage_copy['start_time'] - min_start) * 1000
                    else:
                        relative_ms = 0
                    stage_copy['start_time'] = synthetic_start + relative_ms / 1000
                    merged['stages'].append(stage_copy)

                for microservice in perf.get('microservices') or []:
                    ms_copy = dict(microservice)
                    ms_copy['name'] = f"{message_prefix}.{ms_copy.get('name', 'microservice')}"
                    merged['microservices'].append(ms_copy)

                for llm_call in perf.get('llm_calls') or []:
                    llm_copy = dict(llm_call)
                    llm_copy['service_name'] = f"{message_prefix}.{llm_copy.get('service_name', 'LLM')}"
                    merged['llm_calls'].append(llm_copy)

                merged['total_duration_ms'] += block_duration
                merged['microservices_total_ms'] += perf.get('microservices_total_ms') or 0
                merged['llm_total_cost_rub'] += perf.get('llm_total_cost_rub') or 0
                merged['llm_total_tokens'] += perf.get('llm_total_tokens') or 0
                synthetic_start += block_duration / 1000
            return merged

        messages = list(MessageLog.objects.filter(
            session_id=session_id
        ).order_by('timestamp')[:50])

        performance_items = []
        for msg in messages:
            if msg.metadata and isinstance(msg.metadata, dict) and 'performance' in msg.metadata:
                performance_items.append(
                    {
                        'id': msg.id,
                        'direction': msg.direction,
                        'performance': msg.metadata['performance'],
                    }
                )

        performance_data = merge_session_performance(performance_items)

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
