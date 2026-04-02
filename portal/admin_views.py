"""
Административные представления для портала

АВТОР: Claude Sonnet
ОБНОВЛЕНО: 2026-04-02
ИЗМЕНЕНИЯ:
- Использование UserCompanyMembership вместо UserProfile.role
- Использование mixins для контроля доступа
- Фильтрация по company_id
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import JsonResponse
from portal.models import UserProfile, AIPrompt
from portal.mixins import get_primary_membership
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
    Главная страница административного интерфейса УК

    ДОСТУП: direktor_uk, django_admin (через middleware будет редирект для non-superuser)
    """
    # Проверка staff
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        messages.warning(request, 'Вы не привязаны к компании')
        return redirect('portal:no_membership')

    # Фильтрация по компании
    company_id = membership.company_id

    # Статистика по пользователям компании
    from work_orders.models import UserCompanyMembership

    user_stats = get_user_statistics(company_id)

    context = {
        'company': membership.company,
        'department': membership.department,
        'user_role': membership.role_code,
        'total_users': user_stats['total'],
        'django_admin_count': user_stats['by_role'].get('Django администратор', 0),
        'director_count': user_stats['by_role'].get('Директор УК', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'resident_count': user_stats['by_role'].get('Житель', 0),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(company_id),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
    }

    return render(request, 'portal/admin_page.html', context)


@login_required
def director_page(request):
    """
    Отдельная страница для Директора УК

    ДОСТУП: direktor_uk (ограничение через DirectorMixin в Class-Based Views)
    """
    # Проверка staff
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        messages.warning(request, 'Вы не привязаны к компании')
        return redirect('portal:no_membership')

    # Проверка роли
    if membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_id = membership.company_id

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_id)

    context = {
        'company': membership.company,
        'department': membership.department,
        'user_role': membership.role_code,
        'total_users': user_stats['total'],
        'django_admin_count': user_stats['by_role'].get('Django администратор', 0),
        'director_count': user_stats['by_role'].get('Директор УК', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'resident_count': user_stats['by_role'].get('Житель', 0),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(company_id),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
    }

    return render(request, 'portal/director_page.html', context)


@login_required
def chief_engineer_page(request):
    """
    Страница Главного инженера

    ДОСТУП: chief_engineer
    ПРАВА:
    - Видит всю компанию (все подразделения)
    - Может перераспределять обращения
    - Может переводить в статус "on_hold"
    - Может переоткрывать из completed
    """
    # Проверка staff
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        messages.warning(request, 'Вы не привязаны к компании')
        return redirect('portal:no_membership')

    # Проверка роли
    if membership.role_code != 'chief_engineer':
        messages.error(request, 'Доступ разрешен только Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_id = membership.company_id

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_id)

    context = {
        'company': membership.company,
        'department': membership.department,
        'user_role': membership.role_code,
        'total_users': user_stats['total'],
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'user_stats': user_stats,
    }

    return render(request, 'portal/chief_engineer_page.html', context)


def get_user_statistics(company_id=None):
    """
    Получить статистику по пользователям

    ПАРАМЕТРЫ:
    - company_id: фильтрация по компании (если указана)
    """
    from work_orders.models import UserCompanyMembership

    memberships = UserCompanyMembership.objects.filter(is_active=True)

    if company_id:
        memberships = memberships.filter(company_id=company_id)

    stats = {
        'total': memberships.count(),
        'by_role': {},
        'active_recently': memberships.filter(
            user__last_login__isnull=False
        ).count(),
    }

    # Считаем по ролям (используем ROLE_CHOICES из UserCompanyMembership)
    from work_orders.models import UserCompanyMembership as UCM

    for role_code, role_name in UCM.ROLE_CHOICES:
        count = memberships.filter(role_code=role_code).count()
        stats['by_role'][role_name] = count

    return stats


def get_file_statistics(company_id=None):
    """
    Получить статистику по файлам

    ПАРАМЕТРЫ:
    - company_id: фильтрация по компании (если указана)
    """
    files = UserFile.objects.all()

    # Фильтрация по пользователям компании
    if company_id:
        from work_orders.models import UserCompanyMembership
        user_ids = UserCompanyMembership.objects.filter(
            company_id=company_id,
            is_active=True
        ).values_list('user_id', flat=True)
        files = files.filter(user_id__in=user_ids)

    stats = {
        'total': files.count(),
        'total_size': sum(f.file_size for f in files) if files.exists() else 0,
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