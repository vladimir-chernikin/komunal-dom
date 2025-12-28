from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404
from django.conf import settings
from .models import UserProfile

# Импорты для КЛАДР статистики
try:
    from kladr.models import KladrAddressObject, Building, ServiceArea
    KLADR_AVAILABLE = True
except ImportError:
    KLADR_AVAILABLE = False


def main_page(request):
    """Главная страница - ООО Аспект"""
    return render(request, 'portal/main_page.html')


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
def dashboard(request):
    """Личный кабинет пользователя"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        # Создаем профиль если его нет
        profile = UserProfile.objects.create(user=request.user, role='uk_user')

    # Генерируем session_id для чата
    session_id = f"web_{request.user.id}_{request.session.session_key}"

    context = {
        'user_profile': profile,
        'user_role': profile.role,
        'session_id': session_id,
    }

    # Добавляем статистику для администраторов
    if profile.has_admin_access():
        users = User.objects.select_related('userprofile').all().order_by('username')

        # Статистика по КЛАДР
        kladr_stats = {}
        if KLADR_AVAILABLE:
            kladr_stats = {
                'address_objects': KladrAddressObject.objects.count(),
                'buildings': Building.objects.count(),
                'service_areas': ServiceArea.objects.count(),
            }

        context.update({
            'total_users': users.count(),
            'django_admin_count': users.filter(userprofile__role='django_admin').count(),
            'dba_count': users.filter(userprofile__role='dba').count(),
            'uk_user_count': users.filter(userprofile__role='uk_user').count(),
            'resident_count': users.filter(userprofile__role='resident').count(),
            'kladr_stats': kladr_stats,
        })

    return render(request, 'portal/dashboard.html', context)


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
    """API для получения трассировки диалога"""
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

    # Запрос к БД (без лимита - показываем всю трассировку)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                text,
                direction,
                channel,
                session_id,
                created_at,
                metadata
            FROM message_handler_messagelog
            WHERE session_id LIKE %s
            ORDER BY created_at ASC
        """, [f"{session_id}%"])

        columns = [col[0] for col in cursor.description]
        messages = []
        for row in cursor.fetchall():
            messages.append(dict(zip(columns, row)))

    return JsonResponse({
        'success': True,
        'session_id': session_id,
        'messages': messages,
        'total': len(messages)
    })


@login_required
def api_dialog_sessions(request):
    """API для получения списка сессий"""
    from django.http import JsonResponse
    from django.db import connection

    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, role='resident')

    # Проверка прав доступа
    if not profile.has_admin_access():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    # Запрос к БД - получаем уникальные сессии с информацией о последнем сообщении
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                session_id,
                channel,
                COUNT(*) as message_count,
                MAX(created_at) as last_message
            FROM message_handler_messagelog
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
def api_dialog_full_trace(request):
    """API для генерации полного отчета по трассировке диалога

    ИСПОЛЬЗУЕТ TraceReportService для генерации отчета по шаблону CLAUDE.md
    """
    from django.http import JsonResponse
    import asyncio
    import os
    from datetime import datetime

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

        # Создаем сервис и генерируем отчет
        service = TraceReportService()

        # Генерируем отчет
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report_path = loop.run_until_complete(
                service.generate_trace_report(session_id)
            )
        finally:
            loop.close()

        if not report_path:
            return JsonResponse({'error': 'Не удалось создать отчет - нет сообщений для сессии'}, status=404)

        # Читаем созданный файл для предпросмотра
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Получаем только имя файла
        report_filename = os.path.basename(report_path)

        # Предпросмотр (первые 2000 символов)
        preview_length = 2000
        report_preview = content[:preview_length]
        if len(content) > preview_length:
            report_preview += '\n\n... (текст обрезан)'

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


