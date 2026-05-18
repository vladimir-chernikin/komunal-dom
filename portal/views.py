from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt  # ИСПРАВЛЕНО (2026-01-06): Для API endpoints
from django.contrib import messages  # ИСПРАВЛЕНО (2026-04-06): Добавлен для новых dashboard
from django.contrib.auth.models import User
from django.http import Http404
from django.conf import settings
from django.db import models
from .models import UserProfile
from .mixins import get_primary_membership, get_role_dashboard_url  # ИСПРАВЛЕНО (2026-04-06): Добавлен для новых dashboard
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
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('/admin/')

        dashboard_url, _ = get_role_dashboard_url(request.user)
        return redirect(dashboard_url)

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

        terminal_status_codes = ['completed', 'closed', 'cancelled']
        completed_status_codes = ['completed', 'closed']

        # Сначала получаем подсчеты (до среза)
        work_orders_count = all_work_orders.count()
        active_work_orders = all_work_orders.exclude(
            current_internal_status__short_code_en__in=terminal_status_codes
        ).count()
        completed_work_orders = all_work_orders.filter(
            current_internal_status__short_code_en__in=completed_status_codes
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

            elif session['channel'] == 'maxchat':
                if isinstance(metadata, dict):
                    max_info = metadata.get('max_info', {})
                    if isinstance(max_info, dict):
                        user_info = (
                            max_info.get('username')
                            or max_info.get('name')
                            or max_info.get('first_name')
                        )
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
            session['channel_label'] = {
                'telegram': 'ТГ',
                'maxchat': 'MAX',
                'web': 'Web',
                'api': 'API',
                'test_bot': 'Test',
                'transcriber': 'Phone',
            }.get(session['channel'], session['channel'])

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
    """Совместимый alias: старый executor path использует новый work_orders dashboard."""
    from work_orders.views import ExecutorDashboardView

    view = ExecutorDashboardView.as_view()
    return view(request)


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
