"""
Административные представления для портала
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import JsonResponse
from portal.models import UserProfile, AIPrompt
from file_manager.models import UserFile

# Импорты для КЛАДР статистики
try:
    from kladr.models import KladrAddressObject, Building, ServiceArea
    KLADR_AVAILABLE = True
except ImportError:
    KLADR_AVAILABLE = False


@login_required
def dba_page(request):
    """
    Отдельная страница для DBA менеджера данных
    """
    # Проверка прав доступа (доступно для DBA и django_admin)
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    user_stats = get_user_statistics()
    users = User.objects.select_related('userprofile').all()

    context = {
        'total_users': user_stats['total'],
        'django_admin_count': users.filter(userprofile__role='django_admin').count(),
        'dba_count': users.filter(userprofile__role='dba').count(),
        'executor_count': users.filter(userprofile__role='executor').count(),
        'resident_count': users.filter(userprofile__role='resident').count(),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
    }

    return render(request, 'portal/dba_page.html', context)


def get_user_statistics():
    """Получить статистику по пользователям"""
    users = User.objects.select_related('userprofile').all()

    stats = {
        'total': users.count(),
        'by_role': {},
        'active_recently': users.filter(last_login__isnull=False).count(),
    }

    # Считаем по ролям
    for role, role_name in UserProfile.ROLE_CHOICES:
        count = UserProfile.objects.filter(role=role).count()
        stats['by_role'][role_name] = count

    return stats


def get_file_statistics():
    """Получить статистику по файлам"""
    files = UserFile.objects.all()

    stats = {
        'total': files.count(),
        'total_size': sum(f.file_size for f in files),
        'unique_users': files.values('user').distinct().count(),
    }

    return stats


def get_prompt_statistics():
    """Получить статистику по AI промптам"""
    prompts = AIPrompt.objects.all()

    stats = {
        'total': prompts.count(),
        'active': prompts.filter(is_active=True).count(),
        'by_type': {},
    }

    # Считаем по типам
    for prompt_type, type_name in AIPrompt.PROMPT_TYPES:
        count = prompts.filter(prompt_type=prompt_type).count()
        stats['by_type'][type_name] = count

    return stats


def get_kladr_statistics():
    """Получить статистику по КЛАДР"""
    stats = {
        'address_objects': KladrAddressObject.objects.count() if KLADR_AVAILABLE else 0,
        'buildings': Building.objects.count() if KLADR_AVAILABLE else 0,
        'service_areas': ServiceArea.objects.count() if KLADR_AVAILABLE else 0,
    }
    return stats


# ИСПРАВЛЕНИЕ (2026-02-03): Удалена функция user_management - дубликат /admin/auth/user/
# Полная функциональность доступна в Django Admin


@login_required
def prompt_management(request):
    """
    Управление AI промптами (быстрый доступ)
    """
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    prompts = AIPrompt.objects.all().order_by('prompt_type', 'prompt_id')

    # Подсчет статистики по типам промптов
    prompt_types_with_stats = [
        (name, code, prompts.filter(prompt_type=code).count())
        for name, code in AIPrompt.PROMPT_TYPES
    ]

    context = {
        'prompts': prompts,
        'prompt_types': AIPrompt.PROMPT_TYPES,
        'prompt_types_with_stats': prompt_types_with_stats,
    }

    return render(request, 'portal/prompt_management.html', context)