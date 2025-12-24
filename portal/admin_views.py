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
def admin_page(request):
    """
    Административная страница только для Django-админов
    """
    # Проверка прав доступа
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:main_page')

    # DBA пользователей перенаправляем на их страницу
    if request.user.userprofile.is_dba():
        return redirect('portal:dba_page')

    context = {
        'user_stats': get_user_statistics(),
        'file_stats': get_file_statistics(),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
    }

    return render(request, 'portal/admin_page.html', context)


@login_required
def dba_page(request):
    """
    Отдельная страница для DBA менеджера данных
    """
    # Проверка прав доступа
    if not request.user.userprofile.is_dba():
        messages.error(request, 'Доступ запрещен! Только для DBA.')
        return redirect('portal:main_page')

    context = {
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


@login_required
def user_management(request):
    """
    Управление пользователями (только для админов)
    """
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    users = User.objects.select_related('userprofile').all().order_by('-date_joined')

    # Фильтрация
    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(userprofile__role=role_filter)

    context = {
        'users': users,
        'role_choices': UserProfile.ROLE_CHOICES,
        'current_role': role_filter,
    }

    return render(request, 'portal/user_management.html', context)


@login_required
def prompt_management(request):
    """
    Управление AI промптами (быстрый доступ)
    """
    if not request.user.userprofile.has_admin_access():
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:admin_page')

    prompts = AIPrompt.objects.all().order_by('prompt_type', 'prompt_id')

    context = {
        'prompts': prompts,
        'prompt_types': AIPrompt.PROMPT_TYPES,
    }

    return render(request, 'portal/prompt_management.html', context)