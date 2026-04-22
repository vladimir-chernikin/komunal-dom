from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator


@method_decorator(never_cache, name='__call__')
def admin_login_redirect(request):
    """
    Redirect /admin/login/ → /login/ с сохранением next параметра

    ИСПОЛЬЗУЕТСЯ для унификации точки входа - все пользователи логинятся через /login/

    БЕЗ staff_member_required: иначе цикл редиректа
    """
    next_url = request.GET.get('next', '')
    if next_url and next_url.startswith('/admin/'):
        return redirect(f'/login/?next={next_url}')
    return redirect('/login/')


class CustomAdminSite(admin.AdminSite):
    """
    Кастомный AdminSite с redirect на единый login

    ПЕРЕОПРЕДЕЛЯЕТ:
    - login view → redirect на /login/
    """
    site_header = 'Komunal Dom Administration'
    site_title = 'Komunal Dom Admin'
    index_title = 'Добро пожаловать в панель управления'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('login/', admin_login_redirect, name='login'),
        ]
        # Убираем стандартный login из URL (он будет заменен)
        return custom_urls + [url for url in urls if not hasattr(url, 'name') or url.name != 'login']


# Создаем кастомный admin site
custom_admin_site = CustomAdminSite(name='admin')

