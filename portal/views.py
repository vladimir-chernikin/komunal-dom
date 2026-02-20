from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Для API endpoints
from django.contrib.auth.models import User
from django.http import Http404
from django.conf import settings
from .models import UserProfile
import json  # ИСПРАВЛЕНО (2026-01-05): Добавлен для парсинга metadata

# Импорты для КЛАДР статистики
try:
    from kladr.models import KladrAddressObject, Building, ServiceArea
    KLADR_AVAILABLE = True
except ImportError:
    KLADR_AVAILABLE = False


def welcome(request):
    """Главная страница - приветствие ООО Аспект"""
    return render(request, 'portal/welcome.html')


def test_logo_variants(request):
    """Тестовая страница с вариантами логотипа"""
    from django.http import HttpResponse
    import os
    file_path = os.path.join(settings.BASE_DIR, 'static', 'test_logo_variants.html')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return HttpResponse(f.read())
    except FileNotFoundError:
        return HttpResponse("Файл не найден", status=404)


@login_required
def subscriber_page(request):
    """Страница абонентов"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        # Создаем профиль если его нет
        profile = UserProfile.objects.create(user=request.user, role='resident')

    context = {
        'user_profile': profile,
    }
    return render(request, 'portal/subscriber_page.html', context)


@login_required
def regulatory_chat(request):
    """Страница нормативного чата"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    context = {
        'user_profile': profile,
    }
    return render(request, 'portal/normative_chat.html', context)


@login_required
def dialog_trace_page(request):
    """Страница трассировки диалогов"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Доступ запрещен. Требуются права DBA или администратора.")

    context = {
        'user_profile': profile,
    }
    return render(request, 'portal/dialog_trace.html', context)


@login_required
def dialog_trace_api(request):
    """API для получения трассировки диалога (v3.0 - новый формат)"""
    from django.http import JsonResponse
    from django.db import connection

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # Получаем параметры
    session_id = request.GET.get('session_id')

    if not session_id:
        return JsonResponse({'error': 'Не указан session_id'}, status=400)

    # ИСПРАВЛЕНО (2026-01-05): Загружаем сообщения из dialog_logs
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                message_content,
                direction,
                channel,
                session_id,
                timestamp,
                metadata
            FROM dialog_logs
            WHERE session_id LIKE %s
            ORDER BY timestamp ASC
        """, [f"{session_id}%"])

        columns = [col[0] for col in cursor.description]
        messages = []
        for row in cursor.fetchall():
            msg = dict(zip(columns, row))
            # Парсим metadata если это строка
            if isinstance(msg.get('metadata'), str):
                try:
                    msg['metadata'] = json.loads(msg['metadata'])
                except:
                    msg['metadata'] = {}
            messages.append(msg)

    return JsonResponse({
        'success': True,
        'session_id': session_id,
        'messages': messages,
        'total': len(messages)
    })


@login_required
@csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Отключаем CSRF для API (используем сессионную авторизацию)
def api_dialog_sessions(request):
    """API для получения списка сессий (v3.0 - dialog_logs)"""
    from django.http import JsonResponse
    from django.db import connection

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # ИСПРАВЛЕНО (2026-01-05): Используем dialog_logs вместо message_handler_messagelog
    # ИСПРАВЛЕНО (2026-02-04): Добавлен django_user_id для показа пользователя
    # Запрос к БД - получаем уникальные сессии с информацией о последнем сообщении
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                session_id,
                channel,
                COUNT(*) as message_count,
                MAX(timestamp) as last_message,
                MAX(django_user_id) as django_user_id
            FROM dialog_logs
            GROUP BY session_id, channel
            ORDER BY last_message DESC
            LIMIT 100
        """)

        columns = [col[0] for col in cursor.description]
        sessions = []
        for row in cursor.fetchall():
            sessions.append(dict(zip(columns, row)))

    return JsonResponse({
        'success': True,
        'sessions': sessions
    })


@login_required
@csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Отключаем CSRF для API
def api_dialog_reports(request):
    """API для получения списка файлов отчетов из /tmp/"""
    from django.http import JsonResponse
    import os
    import glob

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # Получаем список файлов отчетов
    # ИСПРАВЛЕНО (2025-12-27): Добавлен паттерн для _tras_diag_*.md файлов
    tmp_dir = '/tmp/'
    patterns = [
        os.path.join(tmp_dir, '*REPORT*.md'),
        os.path.join(tmp_dir, '_tras_diag_*.md')  # ✅ ДОБАВЛЕНО
    ]
    files = []

    for pattern in patterns:
        for filepath in glob.glob(pattern):
            try:
                stat = os.stat(filepath)
                filename = os.path.basename(filepath)
                # Избегаем дубликатов
                if not any(f['name'] == filename for f in files):
                    files.append({
                        'name': filename,
                        'size': stat.st_size,
                        'modified': stat.st_mtime
                    })
            except OSError:
                continue

    # Сортируем по времени изменения (новые сначала)
    files.sort(key=lambda x: x['modified'], reverse=True)

    return JsonResponse({
        'success': True,
        'files': files
    })


@login_required
@csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Отключаем CSRF для API
def api_dialog_report_view(request, filename):
    """API для получения содержимого файла отчета"""
    from django.http import JsonResponse
    import os

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # Безопасность проверка имени файла
    if '..' in filename or '/' in filename:
        return JsonResponse({'error': 'Неверное имя файла'}, status=400)

    filepath = os.path.join('/tmp/', filename)

    if not os.path.exists(filepath):
        return JsonResponse({'error': 'Файл не найден'}, status=404)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        return JsonResponse({
            'success': True,
            'filename': filename,
            'content': content
        })
    except Exception as e:
        return JsonResponse({'error': f'Ошибка чтения файла: {str(e)}'}, status=500)


@login_required
@csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Отключаем CSRF для API
def api_dialog_full_trace(request):
    """API для генерации полного отчета по трассировке диалога

    ИСПОЛЬЗУЕТ TraceReportService для генерации отчета по шаблону CLAUDE.md
    """
    from django.http import JsonResponse
    import os

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # Получаем параметры
    session_id = request.GET.get('session_id')

    if not session_id:
        return JsonResponse({'error': 'Не указан session_id'}, status=400)

    try:
        # Импортируем TraceReportService
        from trace_report_service import TraceReportService
        from asgiref.sync import async_to_sync

        # Создаем сервис и генерируем отчет
        service = TraceReportService()

        # Генерируем отчет (правильный вызов async метода через async_to_sync)
        generate_report = async_to_sync(service.generate_trace_report)
        report_path = generate_report(session_id)

        if not report_path:
            return JsonResponse({'error': 'Не удалось создать отчет - нет сообщений для сессии'}, status=404)

        # Читаем созданный файл для предпросмотра
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Получаем только имя файла
        report_filename = os.path.basename(report_path)

        # Полный текст для предпросмотра (без обрезки)
        report_preview = content

        return JsonResponse({
            'success': True,
            'report_filename': report_filename,
            'report_url': f'/admin-uk/dialog-trace/{report_filename}/',
            'report_preview': report_preview,
            'report_size': len(content),
            'session_id': session_id
        })

    except ImportError as e:
        return JsonResponse({'error': f'Module ImportError: {str(e)}'}, status=500)
    except Exception as e:
        import traceback
        return JsonResponse({
            'error': f'Ошибка генерации отчета: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)


@login_required
def dialog_report_view_page(request, filename):
    """Страница просмотра файла отчета"""
    import os

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Доступ запрещен. Требуются права DBA или администратора.")

    # Безопасность проверка имени файла
    if '..' in filename or '/' in filename:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Неверное имя файла")

    filepath = os.path.join('/tmp/', filename)

    if not os.path.exists(filepath):
        raise Http404("Файл не найден")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Получаем информацию о файле
        stat = os.stat(filepath)
        file_size = stat.st_size
        file_size_formatted = f"{file_size / 1024:.1f} КБ" if file_size > 1024 else f"{file_size} Б"
        file_modified = stat.st_mtime

        context = {
            'user_profile': profile,
            'filename': filename,
            'content': content,
            'file_size': file_size_formatted,
            'file_modified': file_modified,
        }
        return render(request, 'portal/dialog_report_view.html', context)

    except Exception as e:
        from django.http import HttpResponse
        return HttpResponse(f"Ошибка чтения файла: {str(e)}", status=500)


@login_required
def executor_dashboard(request):
    """Кабинет исполнителя - просмотр заявок"""
    from django.db import connection
    from datetime import datetime, timedelta, timezone

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='uk_user')

    # Получаем параметры фильтрации
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '')

    # TODO: Определить категорию услуг исполнителя
    # Пока показываем все заявки, позже можно добавить:
    # - профиль исполнителя с полем category (Электричество/Сантехника/и т.д.)
    # - фильтрацию по category

    # Базовый SQL запрос для получения заявок
    sql_base = """
        SELECT
            r.id,
            r.request_uuid,
            r.created_at,
            r.user_name,
            r.user_phone,
            r.street_name,
            r.house_number,
            r.apartment_number,
            r.entrance,
            r.description,
            r.status,
            r.service_name,
            r.urgency_level,
            rc.category_name as service_category,
            rst.type_name as incident_type,
            r.assigned_to
        FROM bot_service_requests r
        LEFT JOIN services_catalog s ON r.service_id = s.service_id
        LEFT JOIN ref_categories rc ON s.category_id = rc.category_id
        LEFT JOIN ref_service_types rst ON s.type_id = rst.type_id
        WHERE 1=1
    """

    params = []

    # Фильтр по статусу
    if status_filter:
        sql_base += " AND r.status = %s"
        params.append(status_filter)

    # Поиск
    if search_query:
        sql_base += " AND (r.user_name ILIKE %s OR r.description ILIKE %s OR r.street_name ILIKE %s)"
        search_pattern = f"%{search_query}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    # Сортировка по дате (новые сначала)
    sql_base += " ORDER BY r.created_at DESC"

    # Выполняем запрос
    with connection.cursor() as cursor:
        cursor.execute(sql_base, params)
        columns = [col[0] for col in cursor.description]
        requests = []
        for row in cursor.fetchall():
            req = dict(zip(columns, row))
            # Форматируем дату
            if req['created_at']:
                req['created_at_formatted'] = req['created_at'].strftime('%d.%m.%Y %H:%M')
            # Формируем адрес
            address_parts = []
            if req['street_name']:
                address_parts.append(req['street_name'])
            if req['house_number']:
                address_parts.append(f"д. {req['house_number']}")
            if req['apartment_number']:
                address_parts.append(f"кв. {req['apartment_number']}")
            req['address_formatted'] = ', '.join(address_parts) if address_parts else '—'
            # Детали адреса
            req['address_details'] = []
            if req['entrance']:
                req['address_details'].append(f"Подъезд: {req['entrance']}")
            req['address_details_str'] = ', '.join(req['address_details']) if req['address_details'] else ''
            # Категория
            if req['service_category']:
                req['category_badge'] = f'<span class="badge bg-info text-dark">{req["service_category"]}</span>'
            else:
                req['category_badge'] = '—'

            # Вычисляем просрочку для аварийных заявок
            req['is_overdue'] = False
            req['remaining_seconds'] = 0
            req['remaining_time_formatted'] = ''
            req['status_display'] = req['status']  # Для отображения в колонке Статус
            req['deadline_at'] = None

            if req['urgency_level'] == 'emergency' and req['assigned_to'] is None:
                now = datetime.now(timezone.utc)
                time_diff = now - req['created_at']
                total_seconds = time_diff.total_seconds()
                arrival_deadline = 30 * 60  # 30 минут = 1800 секунд

                if total_seconds < 300:  # < 5 минут
                    # Новая, мигает - обратный отсчёт до 5 минут
                    req['remaining_seconds'] = int(300 - total_seconds)
                    mins = req['remaining_seconds'] // 60
                    secs = req['remaining_seconds'] % 60
                    req['remaining_time_formatted'] = f"{mins}:{secs:02d}"
                    req['status_display'] = 'Новая'
                elif total_seconds < arrival_deadline:  # 5-30 минут
                    # Показать таймер до прибытия (30 минут от создания)
                    req['is_overdue'] = True
                    remaining_arrival = int(arrival_deadline - total_seconds)
                    req['remaining_seconds'] = remaining_arrival  # Для JavaScript обновления
                    mins = remaining_arrival // 60
                    secs = remaining_arrival % 60
                    req['remaining_time_formatted'] = f"{mins}:{secs:02d}"
                    req['status_display'] = req['remaining_time_formatted']

                    # Обновляем статус в БД на overdue
                    if req['status'] != 'overdue':
                        cursor.execute(
                            "UPDATE bot_service_requests SET status = 'overdue', updated_at = NOW() WHERE id = %s",
                            [req['id']]
                        )
                        req['status'] = 'overdue'
                else:  # > 30 минут
                    # Просрочена прибытие - показать сколько просрочено
                    req['is_overdue'] = True
                    overdue_arrival = int(total_seconds - arrival_deadline)  # Сколько просрочено
                    mins = overdue_arrival // 60
                    secs = overdue_arrival % 60
                    req['status_display'] = f"-{mins}:{secs:02d}"  # Например: -5:23

                    # Обновляем статус в БД на overdue
                    if req['status'] != 'overdue':
                        cursor.execute(
                            "UPDATE bot_service_requests SET status = 'overdue', updated_at = NOW() WHERE id = %s",
                            [req['id']]
                        )
                        req['status'] = 'overdue'

            requests.append(req)

    # Разделяем на "Мои заявки" (assigned_to = current_user_id) и "Доступные"
    my_requests = [r for r in requests if r['assigned_to'] == request.user.id]
    available_requests = [r for r in requests if r['assigned_to'] is None]

    # Сортировка: просроченные аварийные сверху, затем новые аварийные, затем остальные
    def sort_key(req):
        # Приоритет 1: просроченные аварийные
        if req.get('is_overdue'):
            return (0, req['created_at'])
        # Приоритет 2: аварийные с обратным отсчётом
        elif req.get('urgency_level') == 'emergency' and req.get('remaining_seconds', 0) > 0:
            return (1, req['created_at'])
        # Приоритет 3: остальные по дате (новые сначала)
        else:
            return (2, -req['created_at'].timestamp())

    my_requests.sort(key=sort_key)
    available_requests.sort(key=sort_key)

    context = {
        'user_profile': profile,
        'my_requests': my_requests,
        'available_requests': available_requests,
        'status': status_filter,
        'q': search_query,
    }
    return render(request, 'portal/executor_dashboard.html', context)


@login_required
def executor_take_request(request, request_id):
    """Взять заявку в работу"""
    from django.http import JsonResponse
    from django.db import connection

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='uk_user')

    # Проверка прав - только исполнители и сотрудники УК могут брать заявки
    if not profile.is_employee():
        return JsonResponse({
            'success': False,
            'error': 'Только исполнители могут брать заявки в работу'
        }, status=403)

    # Проверяем метод запроса
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Метод не поддерживается'
        }, status=405)

    # Проверяем существование заявки и что она свободна
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, assigned_to, status
            FROM bot_service_requests
            WHERE id = %s
        """, [request_id])

        row = cursor.fetchone()

        if not row:
            return JsonResponse({
                'success': False,
                'error': 'Заявка не найдена'
            }, status=404)

        request_db_id, assigned_to, status = row

        # Проверяем, что заявка свободна
        if assigned_to is not None:
            return JsonResponse({
                'success': False,
                'error': 'Заявка уже взята в работу другим исполнителем'
            }, status=400)

        # Назначаем заявку текущему пользователю
        cursor.execute("""
            UPDATE bot_service_requests
            SET assigned_to = %s,
                status = 'in_work',
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, status, assigned_to
        """, [request.user.id, request_id])

        updated_row = cursor.fetchone()

    return JsonResponse({
        'success': True,
        'message': 'Заявка успешно взята в работу',
        'request_id': updated_row[0],
        'status': updated_row[1],
        'assigned_to': updated_row[2]
    })
