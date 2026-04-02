"""
Mixins для ролйного контроля доступа в портале

АВТОР: Claude Sonnet
ДАТА: 2026-04-02
НАЗНАЧЕНИЕ:
- Базовые миксины для Staff интерфейсов
- Проверка ролей через UserCompanyMembership
- Фильтрация по компании и подразделению

ИЕРАРХИЯ РОЛӖ:
1._superuser (Django Admin) → полный доступ к /admin/
2. direktor_uk (Директор УК) → управление компанией
3. chief_engineer (Главный инженер) → перераспределение, статусы
4. executor (Исполнитель) → свои заявки + пул
5. resident (Житель) → только свои заявки

ИСПОЛЬЗОВАНИЕ:
```python
from portal.mixins import StaffRequiredMixin, DirectorMixin

class DirectorView(StaffRequiredMixin, DirectorMixin, View):
    pass
```
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied


class StaffRequiredMixin:
    """
    Базовый миксин для всех Staff интерфейсов

    ПРОВЕРЯЕТ:
    - user.is_staff = true (может входить в систему)
    - user.is_authenticated = true (авторизован)
    - UserCompanyMembership существует (есть привязка к компании)

    ДОБАВЛЯЕТ в request:
    - request.user_company_id
    - request.user_department_id
    - request.user_role_code
    - request.user_primary_membership

    ПРИ ОШИБКЕ:
    - Если не staff → redirect на /
    - Если нет membership → redirect на /no-membership/
    """

    def dispatch(self, request, *args, **kwargs):
        # Проверка авторизации
        if not request.user.is_authenticated:
            return redirect('/')

        # Проверка staff
        if not request.user.is_staff:
            return redirect('/')

        # Проверка membership
        if not hasattr(request, 'user_primary_membership') or request.user_primary_membership is None:
            return redirect('/no-membership/')

        return super().dispatch(request, *args, **kwargs)


class DirectorMixin(StaffRequiredMixin):
    """
    Миксин для Директора УК (direktor_uk)

    ПРАВА:
    - Видит всю компанию (все подразделения)
    - Может создавать пользователя̆ в своей компании
    - Может настраивать SLA и услуги
    - НЕ может создавать Django-админов
    - НЕ может править общие справочники (НСИ)

    ПРИ ОШИБКЕ:
    - Если роль не direktor_uk → PermissionDenied
    """

    def dispatch(self, request, *args, **kwargs):
        # Сначала проверяем базовые требования
        response = super().dispatch(request, *args, **kwargs)
        if response:
            return response

        # Проверка роли
        if request.user_role_code != 'direktor_uk':
            raise PermissionDenied("Доступ разрешен только Директорам УК")

        return super().dispatch(request, *args, **kwargs)


class ChiefEngineerMixin(StaffRequiredMixin):
    """
    Миксин для Главного инженера (chief_engineer)

    ПРАВА:
    - Видит всю компанию (все подразделения)
    - Может перераспределять обращения (переназначать)
    - Может переводить в статус "on_hold" (Отложен)
    - Может переоткрывать из completed
    - Может видеть все заявки компании

    ПРИ ОШИБКЕ:
    - Если роль не chief_engineer → PermissionDenied
    """

    def dispatch(self, request, *args, **kwargs):
        # Сначала проверяем базовые требования
        response = super().dispatch(request, *args, **kwargs)
        if response:
            return response

        # Проверка роли
        if request.user_role_code != 'chief_engineer':
            raise PermissionDenied("Доступ разрешен только Главным инженерам")

        return super().dispatch(request, *args, **kwargs)


class ExecutorMixin(StaffRequiredMixin):
    """
    Миксин для Исполнителя (executor)

    ПРАВА:
    - Видит свои заявки + пул подразделения
    - Может самоназначаться
    - НЕ может перераспределять
    - Фильтрация по department_id

    ПРИ ОШИБКЕ:
    - Если роль не executor → PermissionDenied
    """

    def dispatch(self, request, *args, **kwargs):
        # Сначала проверяем базовые требования
        response = super().dispatch(request, *args, **kwargs)
        if response:
            return response

        # Проверка роли
        if request.user_role_code != 'executor':
            raise PermissionDenied("Доступ разрешен только Исполнителям")

        return super().dispatch(request, *args, **kwargs)


class ResidentMixin(LoginRequiredMixin):
    """
    Миксин для Жителя (resident)

    ПРАВА:
    - Видит только свои заявки
    - Видит внешние статусы
    - Может переоткрывать (если разрешено)

    ОТЛИЧИЕ от StaffRequiredMixin:
    - Не требует is_staff
    - Не требует UserCompanyMembership

    ПРИ ОШИБКЕ:
    - Если не авторизован → redirect на login
    """

    def dispatch(self, request, *args, **kwargs):
        # Проверка авторизации
        if not request.user.is_authenticated:
            return redirect('/')

        return super().dispatch(request, *args, **kwargs)


class CompanyFilterMixin:
    """
    Миксин для фильтрации queryset по компании

    ИСПОЛЬЗУЕТ:
    - request.user_company_id (из CompanyMembershipMiddleware)

    ПРИМЕР:
    ```python
    class MyCompanyOrdersView(CompanyFilterMixin, ListView):
        model = WorkOrder
        template_name = 'my_orders.html'

        def get_queryset(self):
            qs = super().get_queryset()
            return self.filter_by_company(qs)
    ```
    """

    def filter_by_company(self, queryset):
        """
        Фильтрация queryset по компании пользователя
        """
        if hasattr(self.request, 'user_company_id') and self.request.user_company_id:
            return queryset.filter(company_id=self.request.user_company_id)
        return queryset.none()  # Нет компании - нет данных

    def filter_by_department(self, queryset):
        """
        Фильтрация queryset по подразделению пользователя
        """
        if hasattr(self.request, 'user_department_id') and self.request.user_department_id:
            return queryset.filter(department_id=self.request.user_department_id)
        return queryset.none()  # Нет подразделения - нет данных


def get_primary_membership(user):
    """
    Возвращает primary UserCompanyMembership для пользователя

    ИСПОЛЬЗУЕТСЯ в views для получения компании и роли

    ПРИМЕР:
    ```python
    membership = get_primary_membership(request.user)
    if membership:
        company = membership.company
        role = membership.role_code
    ```

    ВОЗВРАЩАЕТ:
    - UserCompanyMembership или None
    """
    if not user.is_staff:
        return None

    try:
        from work_orders.models import UserCompanyMembership
        return UserCompanyMembership.objects.filter(
            user=user,
            is_primary=True,
            is_active=True,
            date_to__isnull=True
        ).select_related('company', 'department').first()
    except Exception:
        return None
