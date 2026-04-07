"""
Декораторы для проверки прав доступа в файловом менеджере
"""
from django.http import HttpResponseForbidden
from functools import wraps

def file_access_required(view_func):
    """
    Декоратор для проверки прав доступа к файловому менеджеру
    Разрешает доступ: staff пользователи (is_staff=True)
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Требуется авторизация")

        if not request.user.is_staff:
            return HttpResponseForbidden("Недостаточно прав для доступа к файловому менеджеру")

        return view_func(request, *args, **kwargs)
    return _wrapped_view

def admin_access_required(view_func):
    """
    Декоратор для проверки административных прав
    Разрешает доступ: Директор УК, Django-админ
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseForbidden("Требуется авторизация")

        try:
            profile = request.user.userprofile
            if not profile.has_admin_access():
                return HttpResponseForbidden("Требуются административные права")
        except:
            return HttpResponseForbidden("Профиль пользователя не найден")

        return view_func(request, *args, **kwargs)
    return _wrapped_view