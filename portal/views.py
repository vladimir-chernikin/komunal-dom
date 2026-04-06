from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Для API endpoints
from django.contrib import messages  # ИСПРАВЛЕНО (2026-04-06): Добавлен для новых dashboard
from django.contrib.auth.models import User
from django.http import Http404
from django.conf import settings
from .models import UserProfile
from .mixins import get_primary_membership  # ИСПРАВЛЕНО (2026-04-06): Добавлен для новых dashboard
from nsi.models import Company
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


def landing(request):
    """Стартовая страница для незарегистрированных пользователей"""
    from django.contrib.auth.forms import AuthenticationForm

    # Получаем список активных компаний
    companies = Company.objects.filter(is_active=True).order_by('name')

    context = {
        'companies': companies,
    }

    return render(request, 'portal/landing.html', context)


def aspect_landing(request):
    """Стартовая страница для aspect.komunal-dom.ru"""
    # Получаем информацию о компании "Аспект"
    companies = Company.objects.filter(is_active=True).order_by('name')

    context = {
        'companies': companies,
    }

    return render(request, 'portal/aspect_landing.html', context)


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

    # Получаем membership пользователя
    from portal.mixins import get_primary_membership
    membership = get_primary_membership(request.user)

    context = {
        'user_profile': profile,
    }

    # Добавляем информацию о компании, если есть
    if membership:
        context['company'] = membership.company
        context['membership'] = membership

        # Получаем заявки жителя
        from work_orders.models import WorkOrder
        all_work_orders = WorkOrder.objects.filter(
            resident_user=request.user,
            is_test=False
        ).select_related(
            'current_internal_status', 'service'
        ).order_by('-created_at')

        # Сначала получаем подсчеты (до среза)
        work_orders_count = all_work_orders.count()
        active_work_orders = all_work_orders.filter(
            current_internal_status__short_code_en__in=['accepted_by_executor', 'in_progress']
        ).count()
        completed_work_orders = all_work_orders.filter(
            current_internal_status__short_code_en='completed'
        ).count()

        # Потом применяем срез для отображения
        user_work_orders = all_work_orders[:5]  # Последние 5 заявок

        context['work_orders'] = user_work_orders
        context['work_orders_count'] = work_orders_count
        context['active_work_orders'] = active_work_orders
        context['completed_work_orders'] = completed_work_orders

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
    """API для получения списка сессий (v.3.1 - с информацией о пользователе)"""
    from django.http import JsonResponse
    from django.db import connection
    from django.contrib.auth.models import User

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # ИСПРАВЛЕНО (2026-03-05): Добавлена информация о пользователе (username, telegram login, API NOMER)
    # Запрос к БД - получаем уникальные сессии с информацией о последнем сообщении и metadata
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                dl.session_id,
                dl.channel,
                COUNT(*) as message_count,
                MAX(dl.timestamp) as last_message,
                MAX(dl.django_user_id) as django_user_id,
                (
                    SELECT metadata
                    FROM dialog_logs
                    WHERE session_id = dl.session_id AND channel = dl.channel
                    AND metadata IS NOT NULL
                    LIMIT 1
                ) as sample_metadata
            FROM dialog_logs dl
            GROUP BY dl.session_id, dl.channel
            ORDER BY last_message DESC
            LIMIT 100
        """)

        columns = [col[0] for col in cursor.description]
        sessions = []
        for row in cursor.fetchall():
            session = dict(zip(columns, row))

            # Парсим metadata если есть
            metadata = session.get('sample_metadata')
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}

            # Определяем информацию о пользователе
            user_info = None

            if session['channel'] == 'web':
                # Для web - получаем username из django_user_id
                if session.get('django_user_id'):
                    try:
                        user = User.objects.get(id=session['django_user_id'])
                        user_info = user.username
                    except User.DoesNotExist:
                        user_info = f"UserID:{session['django_user_id']}"

            elif session['channel'] == 'telegram':
                # Для telegram - пробуем получить username из metadata
                if isinstance(metadata, dict):
                    telegram_info = metadata.get('telegram_info', {})
                    if isinstance(telegram_info, dict):
                        user_info = telegram_info.get('username') or telegram_info.get('first_name')
                # Fallback: показываем django_user_id если есть
                if not user_info and session.get('django_user_id'):
                    user_info = f"UserID:{session['django_user_id']}"

            elif session['channel'] == 'api':
                # Для API - получаем NOMER из metadata
                if isinstance(metadata, dict):
                    api_info = metadata.get('api_info', {})
                    if isinstance(api_info, dict):
                        user_info = api_info.get('nomer')

            # Добавляем user_info в сессию
            session['user_info'] = user_info

            # Удаляем sample_metadata (не нужен на фронтенде)
            del session['sample_metadata']

            sessions.append(session)

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
    from datetime import datetime, timezone
    from work_orders.models import WorkOrder, WorkOrderStatusRef

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='uk_user')

    # Получаем membership для определения department
    from portal.mixins import get_primary_membership
    membership = get_primary_membership(request.user)

    if not membership:
        return render(request, 'executor_dashboard.html', {
            'user_profile': profile,
            'my_requests': [],
            'available_requests': [],
            'error': 'У вас нет привязки к компании'
        })

    # Получаем параметры фильтрации
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '')

    # Базовый QuerySet заявок для отдела исполнителя
    work_orders_qs = WorkOrder.objects.filter(
        is_test=False,
        department_id=membership.department_id
    ).select_related(
        'current_internal_status',
        'service',
        'responsible_user'
    ).order_by('-created_at')

    # Фильтр по статусу
    if status_filter:
        work_orders_qs = work_orders_qs.filter(
            current_internal_status__short_code_en=status_filter
        )

    # Поиск по описанию
    if search_query:
        work_orders_qs = work_orders_qs.filter(
            original_request_text__icontains=search_query
        )

    # Форматируем заявки для шаблона
    requests = []
    for wo in work_orders_qs:
        req = {
            'id': wo.id,
            'work_order_no': wo.work_order_no,
            'created_at': wo.created_at,
            'description': wo.original_request_text,
            'status': wo.current_internal_status.short_code_en if wo.current_internal_status else 'unknown',
            'service_name': wo.service.scenario_name if wo.service else '—',
            'urgency_level': 'emergency' if wo.is_emergency else 'normal',
            'assigned_to': wo.responsible_user_id,
            'priority_code': wo.priority_code,
        }

        # Форматируем дату
        if req['created_at']:
            req['created_at_formatted'] = req['created_at'].strftime('%d.%m.%Y %H:%M')

        # Адрес (заглушка, данные о адресе нужно добавить в модель)
        req['address_formatted'] = f"Объект #{wo.object_id}" if wo.object_id else '—'
        req['address_details'] = []
        req['address_details_str'] = ''

        # Категория
        req['category_badge'] = '—'

        # Вычисляем просрочку для аварийных заявок
        req['is_overdue'] = False
        req['remaining_seconds'] = 0
        req['remaining_time_formatted'] = ''
        req['deadline_at'] = None

        # Маппинг статусов на русский язык
        status_map = {
            'new': 'Новая',
            'accepted_by_executor': 'Принята',
            'in_progress': 'В работе',
            'completed': 'Выполнена',
            'cancelled': 'Отменена',
            'on_hold': 'Отложена',
        }
        req['status_display'] = status_map.get(req['status'], req['status'])

        # Таймер для заявок "В работе"
        if req['status'] == 'in_progress' and req['created_at']:
            now = datetime.now(timezone.utc)
            time_in_work = now - req['created_at']
            total_seconds_work = int(time_in_work.total_seconds())
            mins_work = total_seconds_work // 60
            hrs_work = mins_work // 60
            mins_work = mins_work % 60

            if hrs_work > 0:
                req['status_display'] = f"{hrs_work} ч {mins_work} мин в работе"
            else:
                req['status_display'] = f"{mins_work} мин в работе"

        if req['urgency_level'] == 'emergency' and req['assigned_to'] is None:
            now = datetime.now(timezone.utc)
            time_diff = now - req['created_at']
            total_seconds = time_diff.total_seconds()
            arrival_deadline = 30 * 60  # 30 минут

            if total_seconds < 300:  # < 5 минут
                req['is_take_deadline'] = True
                req['remaining_seconds'] = int(300 - total_seconds)
                mins = req['remaining_seconds'] // 60
                secs = req['remaining_seconds'] % 60
                req['remaining_time_formatted'] = f"{mins}:{secs:02d}"
                req['status_display'] = 'Новая'
            elif total_seconds < arrival_deadline:
                req['is_overdue'] = True
                remaining_arrival = int(arrival_deadline - total_seconds)
                req['remaining_seconds'] = remaining_arrival
                mins = remaining_arrival // 60
                secs = remaining_arrival % 60
                req['remaining_time_formatted'] = f"{mins}:{secs:02d}"
                req['status_display'] = req['remaining_time_formatted']
            else:
                req['is_overdue'] = True
                req['is_late'] = True
                late_seconds = int(total_seconds - arrival_deadline)
                req['remaining_seconds'] = late_seconds
                late_mins = late_seconds // 60
                late_secs = late_seconds % 60
                req['status_display'] = f"{late_mins}:{late_secs:02d} опоздание"

        req['can_mark_arrived'] = False
        requests.append(req)

    # Разделяем на "Мои заявки" и "Доступные"
    my_requests = [r for r in requests if r['assigned_to'] == request.user.id]
    available_requests = [r for r in requests if r['assigned_to'] is None]

    # Сортировка
    def sort_key(req):
        if req.get('is_overdue'):
            return (0, req['created_at'])
        elif req.get('urgency_level') == 'emergency' and req.get('remaining_seconds', 0) > 0:
            return (1, req['created_at'])
        else:
            return (2, -req['created_at'].timestamp())

    my_requests.sort(key=sort_key)
    available_requests.sort(key=sort_key)

    # Считаем счетчики
    all_requests_count = len(my_requests)
    status_new_count = len([r for r in my_requests if r['status'] in ['new', 'accepted_by_executor']])
    status_in_work_count = len([r for r in my_requests if r['status'] == 'in_progress'])
    status_done_count = len([r for r in my_requests if r['status'] == 'completed'])
    status_cancelled_count = len([r for r in my_requests if r['status'] == 'cancelled'])

    context = {
        'user_profile': profile,
        'my_requests': my_requests,
        'available_requests': available_requests,
        'status': status_filter,
        'q': search_query,
        'all_requests_count': all_requests_count,
        'status_new_count': status_new_count,
        'status_in_work_count': status_in_work_count,
        'status_done_count': status_done_count,
        'status_cancelled_count': status_cancelled_count,
    }
    return render(request, 'portal/executor_dashboard.html', context)


@login_required
def executor_take_request(request, request_id):
    """Взять заявку в работу"""
    from django.http import JsonResponse
    from django.db import connection

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


@login_required
def executor_arrived_request(request, request_id):
    """Подтвердить прибытие на место"""
    from django.http import JsonResponse
    from django.db import connection

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Метод не поддерживается'
        }, status=405)

    with connection.cursor() as cursor:
        # Проверяем существование заявки и что она назначена текущему пользователю
        cursor.execute("""
            SELECT id, assigned_to, status, is_at_scene
            FROM bot_service_requests
            WHERE id = %s
        """, [request_id])

        row = cursor.fetchone()

        if not row:
            return JsonResponse({
                'success': False,
                'error': 'Заявка не найдена'
            }, status=404)

        request_db_id, assigned_to, status, is_at_scene = row

        # Проверяем, что заявка назначена текущему пользователю
        if assigned_to != request.user.id:
            return JsonResponse({
                'success': False,
                'error': 'Заявка не назначена вам'
            }, status=400)

        # Устанавливаем флаг прибытия
        cursor.execute("""
            UPDATE bot_service_requests
            SET is_at_scene = TRUE,
                arrived_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, is_at_scene
        """, [request_id])

        updated_row = cursor.fetchone()

    return JsonResponse({
        'success': True,
        'message': 'Прибытие подтверждено',
        'request_id': updated_row[0],
        'is_at_scene': updated_row[1]
    })


@login_required
def executor_complete_request(request, request_id):
    """Завершить заявку"""
    from django.http import JsonResponse
    from django.db import connection

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Метод не поддерживается'
        }, status=405)

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

        if assigned_to != request.user.id:
            return JsonResponse({
                'success': False,
                'error': 'Заявка не назначена вам'
            }, status=400)

        # Завершаем заявку
        cursor.execute("""
            UPDATE bot_service_requests
            SET status = 'done',
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, status
        """, [request_id])

        updated_row = cursor.fetchone()

    return JsonResponse({
        'success': True,
        'message': 'Заявка завершена',
        'request_id': updated_row[0],
        'status': updated_row[1]
    })


@login_required
def executor_report(request, request_id):
    """Генерация HTML отчета по выполненной заявке"""
    from django.http import HttpResponse
    from django.template import loader
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                r.id,
                r.created_at,
                r.updated_at,
                r.arrived_at,
                r.status,
                r.assigned_to,
                r.user_name,
                r.user_phone,
                r.street_name,
                r.house_number,
                r.apartment_number as apartment,
                r.entrance as address_details,
                r.description,
                r.photo_path,
                COALESCE(r.service_name, '—') as service_name,  -- ИСПРАВЛЕНО (2026-03-25): берем из заявки
                '—' as category_name,  -- ИСПРАВЛЕНО (2026-03-25): service_id NULL, категория недоступна
                u.username as executor_username,
                u.first_name as executor_first_name,
                u.last_name as executor_last_name
            FROM bot_service_requests r
            LEFT JOIN auth_user u ON r.assigned_to = u.id
            WHERE r.id = %s
        """, [request_id])

        row = cursor.fetchone()

        if not row:
            return HttpResponse('<h1>Заявка не найдена</h1>', status=404)

        # Распаковываем данные
        (req_id, created_at, updated_at, arrived_at, status, assigned_to,
         user_name, user_phone, street_name, house_number, apartment,
         address_details, description, photo_path, service_name, category_name,
         executor_username, executor_first_name, executor_last_name) = row

        # Вычисляем временные интервалы
        from datetime import timezone

        # Время до прибытия (создание → прибытие)
        if arrived_at:
            time_to_arrive = arrived_at - created_at
            minutes_to_arrive = int(time_to_arrive.total_seconds() / 60)
        else:
            minutes_to_arrive = None

        # Время в работе (прибытие → выполнение)
        if arrived_at:
            time_work = updated_at - arrived_at
            minutes_work = int(time_work.total_seconds() / 60)
        else:
            minutes_work = None

        # Общее время (создание → выполнение)
        time_total = updated_at - created_at
        minutes_total = int(time_total.total_seconds() / 60)

        # Имя исполнителя
        if executor_first_name or executor_last_name:
            executor_name = f"{executor_first_name or ''} {executor_last_name or ''}".strip()
        else:
            executor_name = executor_username

        # Формируем данные для шаблона
        report_data = {
            'request_id': req_id,
            'created_at': created_at,
            'updated_at': updated_at,
            'arrived_at': arrived_at,
            'status': status,
            'user_name': user_name,
            'user_phone': user_phone,
            'street_name': street_name,
            'house_number': house_number,
            'apartment': apartment,
            'address_details': address_details,
            'description': description,
            'photo_path': photo_path,
            'category_name': category_name,
            'service_name': service_name,
            'executor_name': executor_name,
            'minutes_to_arrive': minutes_to_arrive,
            'minutes_work': minutes_work,
            'minutes_total': minutes_total,
        }

        # Рендерим шаблон
        template = loader.get_template('portal/executor_report.html')
        html = template.render(report_data, request)

        return HttpResponse(html)


@login_required
def executor_upload_photo(request, request_id):
    """Загрузить фото выполненной работы"""
    from django.http import JsonResponse
    from django.db import connection
    import os
    from django.conf import settings
    from django.core.files.storage import default_storage

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Метод не поддерживается'
        }, status=405)

    # Проверяем наличие файла
    if 'photo' not in request.FILES:
        return JsonResponse({
            'success': False,
            'error': 'Файл не загружен'
        }, status=400)

    photo_file = request.FILES['photo']

    # Проверяем тип файла
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png']
    if photo_file.content_type not in allowed_types:
        return JsonResponse({
            'success': False,
            'error': 'Допустимы только JPG и PNG изображения'
        }, status=400)

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

        if assigned_to != request.user.id:
            return JsonResponse({
                'success': False,
                'error': 'Заявка не назначена вам'
            }, status=400)

        # Сохраняем файл
        filename = f'executor_photo_{request_id}_{photo_file.name}'
        path = default_storage.save(f'executor_photos/{filename}', photo_file)
        photo_url = default_storage.url(path)

        # Обновляем заявку
        cursor.execute("""
            UPDATE bot_service_requests
            SET photo_path = %s,
                updated_at = NOW()
            WHERE id = %s
            RETURNING id, photo_path
        """, [path, request_id])

        updated_row = cursor.fetchone()

    return JsonResponse({
        'success': True,
        'message': 'Фото загружено',
        'request_id': updated_row[0],
        'photo_path': updated_row[1],
        'photo_url': photo_url
    })


@login_required
def contractor_dashboard(request):
    """Кабинет подрядчика - перенаправление на work_orders"""
    from work_orders.views import ContractorDashboardView
    view = ContractorDashboardView.as_view()
    return view(request)


# ========== ВРЕМЕННЫЕ VIEW ФУНКЦИИ ДЛЯ НОВЫХ DASHBOARD (2026-04-06) ==========

@login_required
def executor_dashboard_new(request):
    """
    Временная функция для просмотра нового dashboard исполнителя с 3D дизайном

    TODO: После утверждения дизайна - заменить executor_dashboard.html на executor_dashboard_new.html
    """
    membership = get_primary_membership(request.user)
    if not membership or membership.role_code != 'executor':
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    context = {
        'user': request.user,
    }
    return render(request, 'portal/executor_dashboard_new.html', context)


@login_required
def contractor_dashboard_new(request):
    """
    Временная функция для просмотра нового dashboard подрядчика с 3D дизайном

    TODO: После утверждения дизайна - заменить contractor_dashboard.html на contractor_dashboard_new.html
    """
    membership = get_primary_membership(request.user)
    if not membership or membership.role_code != 'contractor':
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    from work_orders.models import UserCompanyMembership
    memberships = UserCompanyMembership.objects.filter(
        user=request.user,
        is_active=True
    ).select_related('company')

    context = {
        'user': request.user,
        'memberships': memberships,
    }
    return render(request, 'work_orders/contractor_dashboard_new.html', context)


@login_required
def subscriber_page_new(request):
    """
    Временная функция для просмотра нового dashboard жителя с 3D дизайном

    TODO: После утверждения дизайна - заменить subscriber_page.html на subscriber_page_new.html
    """
    membership = get_primary_membership(request.user)
    if not membership or membership.role_code != 'resident':
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    from work_orders.models import WorkOrder
    work_orders = WorkOrder.objects.filter(
        resident_user=request.user
    ).order_by('-created_at')[:10]

    context = {
        'user': request.user,
        'company': membership.company if membership else None,
        'work_orders': work_orders,
    }
    return render(request, 'portal/subscriber_page_new.html', context)
