from django.shortcuts import redirect
from django.contrib.auth import logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache


@never_cache
def admin_login_redirect(request):
    """
    Redirect /admin/login/ → /login/ с сохранением next параметра

    ИСПОЛЬЗУЕТСЯ для унификации точки входа - все пользователи логинятся через /login/

    БЕЗ staff_member_required: иначе цикл редиректа!
    """
    next_url = request.GET.get('next', '')

    # Если next не передан, но запрос идет на /admin/login/,
    # сохраняем intent попасть в /admin/
    if not next_url:
        next_url = '/admin/'

    return redirect(f'/login/?next={next_url}')


@require_http_methods(["GET", "POST"])
def custom_logout(request):
    """Кастомный logout view"""
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, 'Вы вышли из системы')
    return redirect('/')
