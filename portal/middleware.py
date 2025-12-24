from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseForbidden
from .models import UserProfile

class AdminAccessMiddleware:
    """Middleware для ограничения доступа к админ-панели Django"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Проверяем если пользователь пытается зайти в админ-панель
        if request.path.startswith('/admin/') and not request.path.startswith('/admin/logout'):
            if request.user.is_authenticated:
                try:
                    profile = request.user.userprofile
                    # Только Django администраторы могут заходить в админ-панель
                    if not profile.is_django_admin():
                        if request.path != '/admin/':
                            # Если это не главная страница админки, просто блокируем
                            return HttpResponseForbidden("Доступ запрещен")
                        else:
                            # Если главная - перенаправляем в личный кабинет
                            return redirect('portal:dashboard')
                except UserProfile.DoesNotExist:
                    # Если профиля нет, создаем и перенаправляем
                    UserProfile.objects.create(user=request.user, role='uk_user')
                    return redirect('portal:dashboard')

        response = self.get_response(request)
        return response