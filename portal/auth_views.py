"""
Кастомная система аутентификации портала

АВТОР: Claude Sonnet
ДАТА: 2026-04-02
НАЗНАЧЕНИЕ:
- Кастомный login с role-based redirect
- Разделение Django Admin (/admin/) и бизнес-интерфейсов (/admin-uk/, /executor/)
- Поддержка UserCompanyMembership

ЛОГИКА REDIRECT:
1. superuser → /admin/ (Django Admin)
2. direktor_uk → /admin-uk/ (Директор УК)
3. chief_engineer → /chief-engineer/ (Главный инженер)
4. executor → /executor/ (Исполнитель)
5. resident → /subscribers/ (Житель)
"""

from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from portal.mixins import get_primary_membership


class CustomLoginView(LoginView):
    """
    Кастомный Login View с role-based redirect

    ОТЛИЧИЕ от стандартного Django Admin login:
    - Принимает всех staff пользователей (не только superuser)
    - Redirect в зависимости от роли
    - Проверяет наличие UserCompanyMembership

    ИСПОЛЬЗУЕТСЯ в landing.html вместо {% url 'admin:login' %}
    """

    template_name = 'portal/login.html'
    form_class = AuthenticationForm

    def form_valid(self, form):
        """
        Успешная аутентификация

        ПРОВЕРКИ:
        1. user.is_staff = true (может входить в систему)
        2. UserCompanyMembership существует (есть привязка к компании)

        REDIRECT:
        - superuser → /admin/
        - direktor_uk → /admin-uk/
        - chief_engineer → /chief-engineer/
        - executor → /executor/
        - resident → /subscribers/
        - если нет membership → /no-membership/
        """
        user = form.get_user()

        # Проверка: is_staff должен быть true
        if not user.is_staff:
            messages.error(
                self.request,
                "У вас нет доступа к системе. Обратитесь к администратору."
            )
            return self.form_invalid(form)

        # Логиним пользователя
        login(self.request, user)

        # Проверка membership
        membership = get_primary_membership(user)
        if not membership:
            messages.warning(
                self.request,
                "Вы не привязаны ни к одной компании. Обратитесь к администратору."
            )
            return redirect('/no-membership/')

        # Redirect в зависимости от роли
        return redirect(self.get_success_url())

    def get_success_url(self):
        """
        Определяет URL redirect в зависимости от роли пользователя
        """
        membership = get_primary_membership(self.request.user)

        if not membership:
            return '/no-membership/'

        role = membership.role_code

        # Redirect по ролям
        if self.request.user.is_superuser:
            # Django Admin
            return '/admin/'
        elif role == 'direktor_uk':
            # Директор УК
            return '/admin-uk/'
        elif role == 'chief_engineer':
            # Главный инженер
            return '/chief-engineer/'
        elif role == 'executor':
            # Исполнитель
            return '/executor/'
        elif role == 'resident':
            # Житель
            return '/subscribers/'
        else:
            # По умолчанию
            return '/welcome/'


@csrf_protect
def custom_login_view(request):
    """
    Функциональный view для кастомного login

    ИСПОЛЬЗУЕТСЯ если нужно больше контроля чем LoginView
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Проверка: is_staff
            if not user.is_staff:
                messages.error(
                    request,
                    "У вас нет доступа к системе. Обратитесь к администратору."
                )
                return render(request, 'portal/login.html', {'form': form})

            # Логиним
            login(request, user)

            # Проверка membership
            membership = get_primary_membership(user)
            if not membership:
                messages.warning(
                    request,
                    "Вы не привязаны ни к одной компании. Обратитесь к администратору."
                )
                return redirect('/no-membership/')

            # Redirect по роли
            if user.is_superuser:
                return redirect('/admin/')
            elif membership.role_code == 'direktor_uk':
                return redirect('/admin-uk/')
            elif membership.role_code == 'chief_engineer':
                return redirect('/chief-engineer/')
            elif membership.role_code == 'executor':
                return redirect('/executor/')
            elif membership.role_code == 'resident':
                return redirect('/subscribers/')
            else:
                return redirect('/welcome/')
    else:
        form = AuthenticationForm(request)

    return render(request, 'portal/login.html', {'form': form})


def no_membership_page(request):
    """
    Страница "Нет привязки к компании"

    ПОКАЗЫВАЕТСЯ когда:
    - user.is_staff = true
    - Нет UserCompanyMembership

    ДЕЙСТВИЯ:
    - Связаться с администратором
    - Выйти из системы
    """
    return render(request, 'portal/no_membership.html')
