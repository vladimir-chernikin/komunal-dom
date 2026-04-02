"""
Middleware для защиты Django Admin и контроля доступа

АВТОР: Claude Sonnet
ДАТА: 2026-04-02
НАЗНАЧЕНИЕ:
1. Защита Django Admin - только для superuser
2. Добавление company_id и department_id в request для авторизованных пользователей
"""

from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseForbidden


class DjangoAdminProtectionMiddleware:
    """
    Защита Django Admin - только superuser

    ПРАВИЛА:
    - Если user.is_superuser = true → разрешен доступ к /admin/
    - Если user.is_staff = true но is_superuser = false → redirect на /admin-uk/
    - Если user не авторизован → redirect на /login/

    ИСТОРИЯ:
    - 2026-04-02: Переписан для использования is_superuser вместо UserProfile.role
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Проверяем только путь /admin/
        if not request.path.startswith('/admin/'):
            return self.get_response(request)

        # Проверяем авторизацию
        if request.user.is_authenticated:
            # Проверяем superuser
            if not request.user.is_superuser:
                # Если staff но не superuser - redirect на /admin-uk/
                if request.user.is_staff:
                    return redirect('/admin-uk/')
                # Если не staff - forbidden
                return HttpResponseForbidden(
                    """
                    <html>
                    <head><title>Доступ запрещен</title></head>
                    <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 100px;">
                        <h1>🚫 Доступ запрещен</h1>
                        <p>У вас нет доступа к панели администрирования Django.</p>
                        <p><a href="/">На главную</a></p>
                    </body>
                    </html>
                    """
                )

        # Superuser или неавторизованный - разрешаем (Django сам разберется с login)
        return self.get_response(request)


class CompanyMembershipMiddleware:
    """
    Добавление компании и подразделения в request

    Для авторизованных staff пользователей добавляет:
    - request.user_company_id
    - request.user_department_id
    - request.user_role_code
    - request.user_primary_membership

    ИСПОЛЬЗУЕТСЯ в views для фильтрации по компании.

    ИСТОРИЯ:
    - 2026-04-02: Создан для работы с UserCompanyMembership
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Только для авторизованных пользователей
        if request.user.is_authenticated and request.user.is_staff:
            try:
                from work_orders.models import UserCompanyMembership

                # Ищем primary membership
                membership = UserCompanyMembership.objects.filter(
                    user=request.user,
                    is_primary=True,
                    is_active=True,
                    date_to__isnull=True
                ).select_related('company', 'department').first()

                if membership:
                    request.user_company_id = membership.company_id
                    request.user_department_id = membership.department_id
                    request.user_role_code = membership.role_code
                    request.user_primary_membership = membership
                else:
                    # Если нет primary - берем любую активную
                    membership = UserCompanyMembership.objects.filter(
                        user=request.user,
                        is_active=True,
                        date_to__isnull=True
                    ).select_related('company', 'department').first()

                    if membership:
                        request.user_company_id = membership.company_id
                        request.user_department_id = membership.department_id
                        request.user_role_code = membership.role_code
                        request.user_primary_membership = membership
                    else:
                        # Нет membership - это проблема!
                        request.user_company_id = None
                        request.user_department_id = None
                        request.user_role_code = None
                        request.user_primary_membership = None

            except Exception:
                # В случае ошибки (например, при миграциях) - игнорируем
                request.user_company_id = None
                request.user_department_id = None
                request.user_role_code = None
                request.user_primary_membership = None

        return self.get_response(request)