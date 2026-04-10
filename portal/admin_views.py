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
from django.utils import timezone
from portal.models import UserProfile, AIPrompt
from portal.mixins import get_primary_membership, get_role_dashboard_url
from file_manager.models import UserFile

# Импорты для КЛАДР статистики
try:
    from kladr.models import KladrAddressObject, Building, ServiceArea
    KLADR_AVAILABLE = True
except ImportError:
    KLADR_AVAILABLE = False


def _workspace_context(request, membership):
    if request.user.is_superuser and not membership:
        return {
            'company': {'name': 'Все компании'},
            'department': None,
            'user_role': 'superuser',
            'company_scope': None,
        }

    return {
        'company': membership.company,
        'department': membership.department,
        'user_role': membership.role_code,
        'company_scope': getattr(request, 'user_company_ids', None) or [membership.company_id],
    }


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
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Статистика по пользователям компании
    from work_orders.models import UserCompanyMembership

    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'department': workspace['department'],
        'user_role': workspace['user_role'],
        'total_users': user_stats['total'],
        'django_admin_count': user_stats['by_role'].get('Django администратор', 0),
        'director_count': user_stats['by_role'].get('Директор УК', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'resident_count': user_stats['by_role'].get('Житель', 0),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(company_scope),
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
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'department': workspace['department'],
        'user_role': workspace['user_role'],
        'total_users': user_stats['total'],
        'django_admin_count': user_stats['by_role'].get('Django администратор', 0),
        'director_count': user_stats['by_role'].get('Директор УК', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'resident_count': user_stats['by_role'].get('Житель', 0),
        'user_stats': user_stats,
        'file_stats': get_file_statistics(company_scope),
        'prompt_stats': get_prompt_statistics(),
        'kladr_stats': get_kladr_statistics() if KLADR_AVAILABLE else {},
        'total_work_orders': 0,  # TODO: получить из WorkOrder
        'active_work_orders': 0,  # TODO: получить из WorkOrder
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

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'chief_engineer':
        messages.error(request, 'Доступ разрешен только Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Статистика по пользователям компании
    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'department': workspace['department'],
        'user_role': workspace['user_role'],
        'total_users': user_stats['total'],
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
        'chief_engineer_count': user_stats['by_role'].get('Главный инженер', 0),
        'user_stats': user_stats,
    }

    return render(request, 'portal/chief_engineer_page.html', context)


def get_user_statistics(company_scope=None):
    """
    Получить статистику по пользователям

    ПАРАМЕТРЫ:
    - company_scope: int или список company_id для фильтрации
    """
    from work_orders.models import UserCompanyMembership

    memberships = UserCompanyMembership.objects.filter(is_active=True)

    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            memberships = memberships.filter(company_id__in=company_scope)
        else:
            memberships = memberships.filter(company_id=company_scope)

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


def get_file_statistics(company_scope=None):
    """
    Получить статистику по файлам

    ПАРАМЕТРЫ:
    - company_scope: int или список company_id для фильтрации
    """
    files = UserFile.objects.all()

    # Фильтрация по пользователям компании
    if company_scope:
        from work_orders.models import UserCompanyMembership
        membership_filter = {'is_active': True}
        if isinstance(company_scope, (list, tuple, set)):
            membership_filter['company_id__in'] = company_scope
        else:
            membership_filter['company_id'] = company_scope
        user_ids = UserCompanyMembership.objects.filter(**membership_filter).values_list('user_id', flat=True)
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


@login_required
def director_residents(request):
    """
    Управление жителями ТСЖ (только своей компании)

    ДОСТУП: direktor_uk, chief_engineer
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно директору и главному инженеру)
    if not request.user.is_superuser and membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем всех пользователей компании (жители + сотрудники)
    from work_orders.models import UserCompanyMembership
    company_memberships = UserCompanyMembership.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            company_memberships = company_memberships.filter(company_id__in=company_scope)
        else:
            company_memberships = company_memberships.filter(company_id=company_scope)
    company_memberships = company_memberships.select_related('user', 'department').order_by('user__username')

    # Разделяем по ролям
    residents = [m for m in company_memberships if m.role_code == 'resident']
    staff = [m for m in company_memberships if m.role_code != 'resident']

    context = {
        'company': workspace['company'],
        'residents': residents,
        'staff': staff,
        'total_residents': len(residents),
        'total_staff': len(staff),
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_residents.html', context)


@login_required
def director_departments(request):
    """
    Управление подразделениями ТСЖ (только своей компании)

    ДОСТУП: direktor_uk, chief_engineer
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно директору и главному инженеру)
    if not request.user.is_superuser and membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем подразделения компании
    from work_orders.models import CompanyDepartment
    departments = CompanyDepartment.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            departments = departments.filter(company_id__in=company_scope)
        else:
            departments = departments.filter(company_id=company_scope)
    departments = departments.select_related('parent_department').order_by('department_name')

    # Статистика по сотрудникам в подразделениях
    from work_orders.models import UserCompanyMembership
    departments_with_stats = []
    for dept in departments:
        staff_count = UserCompanyMembership.objects.filter(
            department_id=dept.id,
            is_active=True
        ).count()
        departments_with_stats.append({
            'department': dept,
            'staff_count': staff_count,
        })

    context = {
        'company': workspace['company'],
        'departments': departments_with_stats,
        'total_departments': departments.count(),
        'can_add_department': bool(membership and membership.role_code == 'direktor_uk'),  # Только директор может добавлять
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_departments.html', context)


@login_required
def director_add_resident(request):
    """
    Добавление жителя/сотрудника директором ТСЖ

    ДОСТУП: direktor_uk, chief_engineer
    """

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно директору и главному инженеру)
    if not request.user.is_superuser and membership.role_code not in ['direktor_uk', 'chief_engineer']:
        messages.error(request, 'Доступ разрешен только Директорам УК и Главным инженерам')
        return redirect('portal:welcome')

    superuser_without_membership = request.user.is_superuser and not membership
    companies = None
    company_id = membership.company_id if membership else None
    selected_company_id = request.POST.get('company') or request.GET.get('company')

    if superuser_without_membership:
        from nsi.models import Company
        companies = Company.objects.filter(is_active=True).order_by('name')
        if selected_company_id:
            try:
                company_id = int(selected_company_id)
            except (TypeError, ValueError):
                company_id = None

    # Обработка формы
    if request.method == 'POST':
        from portal.forms import AddResidentForm
        form = AddResidentForm(request.POST)

        form_valid = form.is_valid()
        company = None
        if superuser_without_membership:
            from nsi.models import Company
            if not company_id:
                form.add_error(None, 'Укажите компанию')
                form_valid = False
            else:
                try:
                    company = Company.objects.get(id=company_id, is_active=True)
                except Company.DoesNotExist:
                    form.add_error(None, 'Выбранная компания недоступна')
                    form_valid = False

        if form_valid:
            # Создаем пользователя
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data.get('email', ''),
                first_name=form.cleaned_data.get('first_name', ''),
                last_name=form.cleaned_data.get('last_name', ''),
                password=form.cleaned_data['password'],
                is_staff=False  # Жители - не staff
            )

            # Получаем или создаем UserProfile
            from portal.models import UserProfile
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'timezone': 'Europe/Moscow',
                    'role': 'uk_user'
                }
            )

            # Получаем подразделение (обязательно для сотрудников)
            from work_orders.models import CompanyDepartment
            department_id = request.POST.get('department')
            department = None
            role_code = form.cleaned_data['role']

            # Для исполнителей и главного инженера department обязателен
            if role_code in ['executor', 'chief_engineer']:
                if not department_id or department_id == '':
                    messages.error(request, 'Для сотрудников обязательно укажите подразделение!')
                    return render(request, 'portal/director_add_resident.html', {
                        'company': workspace['company'],
                        'form': form,
                        'departments': departments,
                        'companies': companies,
                        'selected_company_id': str(company_id) if company_id else '',
                        'superuser_without_membership': superuser_without_membership,
                    })
                try:
                    department = CompanyDepartment.objects.get(
                        id=int(department_id),
                        company_id=company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    messages.error(request, 'Указанное подразделение не найдено!')
                    return render(request, 'portal/director_add_resident.html', {
                        'company': workspace['company'],
                        'form': form,
                        'departments': departments,
                        'companies': companies,
                        'selected_company_id': str(company_id) if company_id else '',
                        'superuser_without_membership': superuser_without_membership,
                    })
            elif department_id and department_id != '':
                # Для жителей department опционален, но если указан - проверяем
                try:
                    department = CompanyDepartment.objects.get(
                        id=int(department_id),
                        company_id=company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    pass

            # Создаем UserCompanyMembership
            from work_orders.models import UserCompanyMembership
            UserCompanyMembership.objects.create(
                user=user,
                company_id=company_id,
                department=department,
                role_code=role_code,
                is_primary=True,
                is_active=True,
                date_from=timezone.now()
            )

            messages.success(request, f'Пользователь {user.username} успешно создан!')
            return redirect('portal:director_residents')
    else:
        from portal.forms import AddResidentForm
        form = AddResidentForm()

    # Получаем подразделения для выбора
    from work_orders.models import CompanyDepartment
    departments = CompanyDepartment.objects.filter(is_active=True)
    if superuser_without_membership and not company_id:
        departments = departments.none()
    elif company_id:
        departments = departments.filter(company_id=company_id)
    departments = departments.select_related('company').order_by('company__name', 'department_name')

    context = {
        'company': workspace['company'],
        'form': form,
        'departments': departments,
        'companies': companies,
        'selected_company_id': str(company_id) if company_id else '',
        'superuser_without_membership': superuser_without_membership,
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_resident.html', context)


@login_required
def director_add_department(request):
    """
    Добавление подразделения директором ТСЖ

    ДОСТУП: direktor_uk (только директор)
    """
    # Проверка staff

    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно только директору)
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    superuser_without_membership = request.user.is_superuser and not membership
    companies = None
    company_id = membership.company_id if membership else None
    selected_company_id = request.POST.get('company') or request.GET.get('company')

    if superuser_without_membership:
        from nsi.models import Company
        companies = Company.objects.filter(is_active=True).order_by('name')
        if selected_company_id:
            try:
                company_id = int(selected_company_id)
            except (TypeError, ValueError):
                company_id = None

    from work_orders.models import CompanyDepartment
    departments = CompanyDepartment.objects.filter(is_active=True)
    if superuser_without_membership and not company_id:
        departments = departments.none()
    elif company_id:
        departments = departments.filter(company_id=company_id)
    departments = departments.select_related('company').order_by('company__name', 'department_name')

    # Обработка формы
    if request.method == 'POST':
        from portal.forms import AddDepartmentForm
        form = AddDepartmentForm(request.POST, departments=departments)

        form_valid = form.is_valid()
        if superuser_without_membership:
            from nsi.models import Company
            if not company_id:
                form.add_error(None, 'Укажите компанию')
                form_valid = False
            elif not Company.objects.filter(id=company_id, is_active=True).exists():
                form.add_error(None, 'Выбранная компания недоступна')
                form_valid = False

        if form_valid:
            # Получаем родительское подразделение (если указан)
            parent_id = request.POST.get('parent_department')
            parent = None
            if parent_id and parent_id != '':
                try:
                    parent = CompanyDepartment.objects.get(
                        id=int(parent_id),
                        company_id=company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    pass

            # Создаем подразделение
            department = CompanyDepartment.objects.create(
                company_id=company_id,
                department_code=form.cleaned_data['department_code'],
                department_name=form.cleaned_data['department_name'],
                parent_department=parent,
                is_active=True,
                is_test=False
            )

            messages.success(request, f'Подразделение "{department.department_name}" успешно создано!')
            return redirect('portal:director_departments')
    else:
        from portal.forms import AddDepartmentForm

        form = AddDepartmentForm(departments=departments)

    context = {
        'company': workspace['company'],
        'form': form,
        'companies': companies,
        'selected_company_id': str(company_id) if company_id else '',
        'superuser_without_membership': superuser_without_membership,
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_department.html', context)


@login_required
def director_edit_department(request, department_id):
    """
    Редактирование подразделения директором ТСЖ

    ДОСТУП: direktor_uk
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли (доступно только директору)
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    from work_orders.models import CompanyDepartment

    # Получаем подразделение
    try:
        department = CompanyDepartment.objects.get(id=department_id)
    except CompanyDepartment.DoesNotExist:
        messages.error(request, 'Подразделение не найдено')
        return redirect('portal:director_departments')

    # Проверка доступа к компании
    company_scope = workspace['company_scope']
    if not request.user.is_superuser:
        if isinstance(company_scope, (list, tuple, set)):
            if department.company_id not in company_scope:
                messages.error(request, 'Доступ к этому подразделению запрещен')
                return redirect('portal:director_departments')
        else:
            if department.company_id != company_scope:
                messages.error(request, 'Доступ к этому подразделению запрещен')
                return redirect('portal:director_departments')

    # Получаем все подразделения для выбора родительского
    departments = CompanyDepartment.objects.filter(
        is_active=True,
        company_id=department.company_id
    ).exclude(id=department_id).select_related('company').order_by('department_name')

    # Обработка формы
    if request.method == 'POST':
        from portal.forms import EditDepartmentForm
        form = EditDepartmentForm(request.POST, departments=departments, instance=department)

        if form.is_valid():
            # Получаем родительское подразделение (если указан)
            parent_id = request.POST.get('parent_department')
            parent = None
            if parent_id and parent_id != '':
                try:
                    parent = CompanyDepartment.objects.get(
                        id=int(parent_id),
                        company_id=department.company_id
                    )
                except CompanyDepartment.DoesNotExist:
                    pass

            # Обновляем подразделение
            department.department_code = form.cleaned_data['department_code']
            department.department_name = form.cleaned_data['department_name']
            department.parent_department = parent
            department.save()

            messages.success(request, f'Подразделение "{department.department_name}" успешно обновлено!')
            return redirect('portal:director_departments')
    else:
        from portal.forms import EditDepartmentForm

        # Инициализируем форму текущими значениями
        initial_data = {
            'department_code': department.department_code,
            'department_name': department.department_name,
            'parent_department': department.parent_department_id if department.parent_department else '',
        }
        form = EditDepartmentForm(initial=initial_data, departments=departments, instance=department)

    context = {
        'company': workspace['company'],
        'department': department,
        'form': form,
        'is_edit': True,
    }

    # Breadcrumbs для возврата на правильный дашборд
    dashboard_url, dashboard_title = get_role_dashboard_url(request.user)
    context['dashboard_url'] = dashboard_url
    context['dashboard_title'] = dashboard_title

    return render(request, 'portal/director_add_department.html', context)


# ========== ВРЕМЕННЫЕ VIEW ФУНКЦИИ ДЛЯ НОВЫХ DASHBOARD (2026-04-06) ==========

@login_required
def director_page_new(request):
    """
    Временная функция для просмотра нового dashboard директора с 3D дизайном

    TODO: После утверждения дизайна - заменить director_page.html на director_page_new.html
    """
    # Проверка доступа
    if not request.user.is_staff:
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    company_scope = workspace['company_scope']

    # Статистика
    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'total_users': user_stats['total'],
        'resident_count': user_stats['by_role'].get('Житель', 0),
    }

    return render(request, 'portal/director_page_new.html', context)


@login_required
def chief_engineer_page_new(request):
    """
    Временная функция для просмотра нового dashboard главного инженера с 3D дизайном

    TODO: После утверждения дизайна - заменить chief_engineer_page.html на chief_engineer_page_new.html
    """
    # Проверка доступа
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.error(request, 'Доступ запрещен!')
            return redirect('portal:welcome')
    else:
        workspace = _workspace_context(request, membership)

    if not request.user.is_superuser and membership.role_code != 'chief_engineer':
        messages.error(request, 'Доступ запрещен!')
        return redirect('portal:welcome')

    company_scope = workspace['company_scope']

    # Статистика
    user_stats = get_user_statistics(company_scope)

    context = {
        'company': workspace['company'],
        'total_users': user_stats['total'],
        'executor_count': user_stats['by_role'].get('Исполнитель', 0),
    }

    return render(request, 'portal/chief_engineer_page_new.html', context)


@login_required
def director_sla(request):
    """
    Управление SLA политиками организации

    ДОСТУП: direktor_uk
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем SLA политики компании
    from work_orders.models import SLAPolicy

    sla_policies = SLAPolicy.objects.filter(is_active=True)
    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            sla_policies = sla_policies.filter(company_id__in=company_scope)
        else:
            sla_policies = sla_policies.filter(company_id=company_scope)

    sla_policies = sla_policies.select_related('company', 'service').order_by('-created_at')

    context = {
        'company': workspace['company'],
        'sla_policies': sla_policies,
        'total_policies': sla_policies.count(),
    }

    return render(request, 'portal/director_sla.html', context)


@login_required
def director_employees(request):
    """
    Управление сотрудниками организации

    ДОСТУП: direktor_uk
    """
    # Получаем membership
    membership = get_primary_membership(request.user)
    if not membership:
        if request.user.is_superuser:
            workspace = _workspace_context(request, membership)
        else:
            messages.warning(request, 'Вы не привязаны к компании')
            return redirect('portal:no_membership')
    else:
        workspace = _workspace_context(request, membership)

    # Проверка роли
    if not request.user.is_superuser and membership.role_code != 'direktor_uk':
        messages.error(request, 'Доступ разрешен только Директорам УК')
        return redirect('portal:welcome')

    # Фильтрация по компании
    company_scope = workspace['company_scope']

    # Получаем сотрудников компании (все роли кроме "Житель")
    from work_orders.models import UserCompanyMembership

    employee_roles = ['direktor_uk', 'chief_engineer', 'executor', 'django_admin']

    employees = UserCompanyMembership.objects.filter(
        is_active=True,
        role_code__in=employee_roles
    )

    if company_scope:
        if isinstance(company_scope, (list, tuple, set)):
            employees = employees.filter(company_id__in=company_scope)
        else:
            employees = employees.filter(company_id=company_scope)

    employees = employees.select_related('user', 'company', 'department').order_by('user__last_name', 'user__first_name')

    context = {
        'company': workspace['company'],
        'employees': employees,
        'total_employees': employees.count(),
    }

    return render(request, 'portal/director_employees.html', context)
