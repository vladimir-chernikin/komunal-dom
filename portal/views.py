from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import Http404
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


