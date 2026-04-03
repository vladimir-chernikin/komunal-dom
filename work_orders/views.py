"""
Views для подсистемы управления заявками ЖКХ
"""
from django.views.generic import TemplateView, DetailView, CreateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, Count, Case, When, IntegerField
from django.urls import reverse_lazy

from .models import (
    WorkOrder, WorkOrderStatusRef, UserCompanyMembership,
    CompanyDepartment, WorkOrderEventLog, RequestIntake,
    WorkOrderStatusHistory
)
from portal.models import ServicesCatalog, ServiceObject
from portal.mixins import get_role_dashboard_url


class ExecutorDashboardView(LoginRequiredMixin, TemplateView):
    """Дашборд исполнителя с двумя табами: Мои заявки + Пул подразделения"""
    template_name = 'work_orders/executor_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем текущего пользователя
        user = self.request.user

        # Получаем членства пользователя в компаниях
        memberships = UserCompanyMembership.objects.filter(
            user=user,
            is_active=True
        ).select_related('company', 'department')

        if not memberships.exists():
            context['error'] = 'У вас нет назначенных ролей в компаниях'
            return context

        # Основное членство
        primary_membership = memberships.filter(is_primary=True).first() or memberships.first()
        context['membership'] = primary_membership
        context['company'] = primary_membership.company
        context['department'] = primary_membership.department

        # Мои заявки (назначенные на пользователя)
        my_requests = WorkOrder.objects.filter(
            responsible_user=user,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')

        # Статистика по моим заявкам
        context['my_requests_new'] = my_requests.filter(current_internal_status__short_code_en='accepted_by_executor').count()
        context['my_requests_in_progress'] = my_requests.filter(current_internal_status__short_code_en='in_progress').count()
        context['my_requests_on_hold'] = my_requests.filter(current_internal_status__short_code_en='on_hold').count()
        context['my_requests_completed'] = my_requests.filter(current_internal_status__short_code_en='completed').count()
        context['my_requests_total'] = my_requests.count()

        # Пул подразделения (заявки, не назначенные на исполнителя)
        pool_requests = WorkOrder.objects.filter(
            department=primary_membership.department,
            responsible_user__isnull=True,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')

        # Статистика по пулу
        context['pool_new'] = pool_requests.filter(current_internal_status__short_code_en='new_registered').count()
        context['pool_total'] = pool_requests.count()

        # Breadcrumbs для возврата на правильный дашборд
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class ExecutorMyRequestsView(LoginRequiredMixin, TemplateView):
    """Список моих заявок"""
    template_name = 'work_orders/executor_my_requests.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Мои заявки
        my_requests = WorkOrder.objects.filter(
            responsible_user=self.request.user,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')

        # Фильтрация по статусу
        status_filter = self.request.GET.get('status')
        if status_filter:
            my_requests = my_requests.filter(current_internal_status__short_code_en=status_filter)

        context['my_requests'] = my_requests
        context['status_filter'] = status_filter

        # Breadcrumbs для возврата на правильный дашборд
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class ExecutorPoolView(LoginRequiredMixin, TemplateView):
    """Пул заявок подразделения"""
    template_name = 'work_orders/executor_pool.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем членство пользователя
        membership = UserCompanyMembership.objects.filter(
            user=self.request.user,
            is_active=True
        ).select_related('department').first()

        if not membership:
            context['error'] = 'У вас нет назначенных ролей'
            return context

        # Пул заявок
        pool_requests = WorkOrder.objects.filter(
            department=membership.department,
            responsible_user__isnull=True,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')

        context['pool_requests'] = pool_requests
        context['department'] = membership.department

        # Breadcrumbs для возврата на правильный дашборд
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class WorkOrderDetailView(LoginRequiredMixin, DetailView):
    """Карточка заявки"""
    model = WorkOrder
    template_name = 'work_orders/work_order_detail.html'
    context_object_name = 'work_order'
    pk_url_kwarg = 'work_order_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # История событий
        events = WorkOrderEventLog.objects.filter(
            work_order=self.object
        ).select_related(
            'author_user', 'new_status', 'old_status'
        ).order_by('-event_datetime')

        context['events'] = events

        # Breadcrumbs для возврата на правильный дашборд
        from portal.mixins import get_role_dashboard_url
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class WorkOrderCreateView(LoginRequiredMixin, CreateView):
    """Форма ручного создания заявки"""
    model = WorkOrder
    template_name = 'work_orders/work_order_create.html'
    fields = ['object', 'service', 'original_request_text', 'priority_code', 'is_emergency']

    def get_success_url(self):
        return reverse_lazy('work_orders:work_order_detail', kwargs={'work_order_id': self.object.id})

    def form_valid(self, form):
        # Получаем членство пользователя
        membership = UserCompanyMembership.objects.filter(
            user=self.request.user,
            is_active=True
        ).select_related('company', 'department').first()

        if not membership:
            form.add_error(None, 'У вас нет назначенных ролей')
            return self.form_invalid(form)

        # Сохраняем заявку
        work_order = form.save(commit=False)
        work_order.company = membership.company
        work_order.department = membership.department
        work_order.creation_source = 'manual_employee'
        work_order.current_internal_status = WorkOrderStatusRef.objects.get(short_code_en='new_registered')
        work_order.created_at = timezone.now()
        work_order.is_test = False
        work_order.save()

        # Создаем событие создания
        WorkOrderEventLog.objects.create(
            work_order=work_order,
            company=work_order.company,
            department=work_order.department,
            event_type_code='created',
            event_datetime=timezone.now(),
            text_value=f'Заявка создана вручную: {work_order.original_request_text[:100]}...',
            author_user=self.request.user,
            is_visible_to_resident=False,
            is_test=False
        )

        return super().form_valid(form)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        # TODO: Добавить фильтрацию сервисов и объектов
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Breadcrumbs для возврата на правильный дашборд
        from portal.mixins import get_role_dashboard_url
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class ManagementListView(LoginRequiredMixin, TemplateView):
    """Управленческий список заявок"""
    template_name = 'work_orders/management_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем членства пользователя (должен быть директор или главный инженер)
        memberships = UserCompanyMembership.objects.filter(
            user=self.request.user,
            is_active=True,
            role_code__in=['direktor_uk', 'chief_engineer']
        ).select_related('company', 'department')

        if not memberships.exists():
            context['error'] = 'У вас нет прав для просмотра управленческого списка'
            return context

        # Получаем заявки компании
        primary_membership = memberships.filter(is_primary=True).first() or memberships.first()

        work_orders = WorkOrder.objects.filter(
            company=primary_membership.company,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object', 'responsible_user', 'department'
        ).order_by('-created_at')

        # Фильтры
        status_filter = self.request.GET.get('status')
        department_filter = self.request.GET.get('department')
        priority_filter = self.request.GET.get('priority')

        if status_filter:
            work_orders = work_orders.filter(current_internal_status__short_code_en=status_filter)
        if department_filter:
            work_orders = work_orders.filter(department_id=department_filter)
        if priority_filter:
            work_orders = work_orders.filter(priority_code=priority_filter)

        context['work_orders'] = work_orders
        context['company'] = primary_membership.company
        context['status_filter'] = status_filter
        context['department_filter'] = department_filter
        context['priority_filter'] = priority_filter

        # Список подразделений для фильтра
        context['departments'] = CompanyDepartment.objects.filter(
            company=primary_membership.company,
            is_active=True
        )

        # Breadcrumbs для возврата на правильный дашборд
        from portal.mixins import get_role_dashboard_url
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class ResidentDashboardView(LoginRequiredMixin, TemplateView):
    """Экран жителя"""
    template_name = 'work_orders/resident_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Заявки жителя
        my_requests = WorkOrder.objects.filter(
            resident_user=self.request.user,
            is_test=False
        ).select_related(
            'current_internal_status', 'service'
        ).order_by('-created_at')

        context['my_requests'] = my_requests
        context['total_requests'] = my_requests.count()
        context['active_requests'] = my_requests.exclude(
            current_internal_status__short_code_en__in=['completed', 'closed', 'cancelled']
        ).count()

        # Breadcrumbs для возврата на правильный дашборд
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class ContractorDashboardView(LoginRequiredMixin, TemplateView):
    """Дашборд подрядчика"""
    template_name = 'work_orders/contractor_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем текущего пользователя
        user = self.request.user

        # Получаем членства пользователя в компаниях (может быть несколько для подрядчика)
        memberships = UserCompanyMembership.objects.filter(
            user=user,
            is_active=True,
            role_code='contractor'
        ).select_related('company', 'department')

        if not memberships.exists():
            context['error'] = 'У вас нет назначенных ролей подрядчика'
            return context

        # Все членства подрядчика
        context['memberships'] = memberships

        # Основное членство
        primary_membership = memberships.filter(is_primary=True).first() or memberships.first()
        context['primary_membership'] = primary_membership
        context['company'] = primary_membership.company
        context['department'] = primary_membership.department

        # Мои заявки (назначенные на подрядчика)
        my_requests = WorkOrder.objects.filter(
            responsible_user=user,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object', 'company'
        ).order_by('-created_at')

        # Статистика по моим заявкам
        context['my_requests_new'] = my_requests.filter(current_internal_status__short_code_en='accepted_by_executor').count()
        context['my_requests_in_progress'] = my_requests.filter(current_internal_status__short_code_en='in_progress').count()
        context['my_requests_on_hold'] = my_requests.filter(current_internal_status__short_code_en='on_hold').count()
        context['my_requests_completed'] = my_requests.filter(current_internal_status__short_code_en='completed').count()
        context['my_requests_total'] = my_requests.count()

        # Пул заявок по всем компаниям подрядчика
        company_ids = memberships.values_list('company_id', flat=True)
        pool_requests = WorkOrder.objects.filter(
            company_id__in=company_ids,
            responsible_user__isnull=True,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object', 'company'
        ).order_by('-created_at')

        # Статистика по пулу
        context['pool_new'] = pool_requests.filter(current_internal_status__short_code_en='new_registered').count()
        context['pool_total'] = pool_requests.count()

        # Breadcrumbs для возврата на правильный дашборд
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


# API для действий над заявками
def api_take_work_order(request, work_order_id):
    """Взять заявку в работу"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(WorkOrder, pk=work_order_id, is_test=False)

    # Проверяем, что заявка не назначена
    if work_order.responsible_user:
        return JsonResponse({'error': 'Заявка уже назначена'}, status=400)

    # Проверяем права пользователя
    membership = UserCompanyMembership.objects.filter(
        user=request.user,
        department=work_order.department,
        is_active=True
    ).first()

    if not membership:
        return JsonResponse({'error': 'У вас нет прав для выполнения этой заявки'}, status=403)

    # Назначаем заявку
    work_order.responsible_user = request.user
    new_status = WorkOrderStatusRef.objects.get(short_code_en='accepted_by_executor')
    work_order.current_internal_status = new_status
    work_order.save()

    # Записываем в историю изменений статусов
    WorkOrderStatusHistory.objects.create(
        work_order=work_order,
        status=new_status,
        changed_by=request.user,
        is_test=False
    )

    # Создаем событие
    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code='assigned',
        event_datetime=timezone.now(),
        text_value=f'Заявка принята исполнителем: {request.user.get_full_name()}',
        author_user=request.user,
        new_responsible_user=request.user,
        is_visible_to_resident=False,
        is_test=False
    )

    return JsonResponse({'success': True, 'redirect_url': f"/work_orders/request/{work_order_id}/"})


def api_start_work_order(request, work_order_id):
    """Начать выполнение заявки"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(WorkOrder, pk=work_order_id, is_test=False)

    # Проверяем, что заявка назначена на текущего пользователя
    if work_order.responsible_user != request.user:
        return JsonResponse({'error': 'Заявка назначена на другого пользователя'}, status=403)

    # Меняем статус на "В работе"
    new_status = WorkOrderStatusRef.objects.get(short_code_en='in_progress')
    work_order.current_internal_status = new_status
    work_order.save()

    # Записываем в историю изменений статусов
    WorkOrderStatusHistory.objects.create(
        work_order=work_order,
        status=new_status,
        changed_by=request.user,
        is_test=False
    )

    # Создаем событие
    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code='status_changed',
        event_datetime=timezone.now(),
        text_value='Заявка переведена в статус "В работе"',
        author_user=request.user,
        new_status=work_order.current_internal_status,
        is_visible_to_resident=True,
        is_test=False
    )

    return JsonResponse({'success': True})


def api_complete_work_order(request, work_order_id):
    """Завершить выполнение заявки"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(WorkOrder, pk=work_order_id, is_test=False)

    # Проверяем, что заявка назначена на текущего пользователя
    if work_order.responsible_user != request.user:
        return JsonResponse({'error': 'Заявка назначена на другого пользователя'}, status=403)

    # Получаем текст решения
    resolution_text = request.POST.get('resolution_text', '')
    if not resolution_text:
        return JsonResponse({'error': 'Необходимо указать текст решения'}, status=400)

    # Меняем статус на "Выполнена"
    new_status = WorkOrderStatusRef.objects.get(short_code_en='completed')
    work_order.current_internal_status = new_status
    work_order.resolution_text = resolution_text
    work_order.save()

    # Создаем событие
    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code='completed',
        event_datetime=timezone.now(),
        text_value='Заявка выполнена',
        author_user=request.user,
        new_status=work_order.current_internal_status,
        is_visible_to_resident=True,
        is_test=False
    )

    # Записываем в историю изменений статусов
    WorkOrderStatusHistory.objects.create(
        work_order=work_order,
        status=new_status,
        changed_by=request.user,
        is_test=False
    )

    return JsonResponse({'success': True})


def api_close_work_order(request, work_order_id):
    """Закрыть заявку"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(WorkOrder, pk=work_order_id, is_test=False)

    # Проверяем права (только директор или главный инженер могут закрывать)
    membership = UserCompanyMembership.objects.filter(
        user=request.user,
        company=work_order.company,
        role_code__in=['direktor_uk', 'chief_engineer'],
        is_active=True
    ).first()

    if not membership:
        return JsonResponse({'error': 'У вас нет прав для закрытия заявок'}, status=403)

    # Проверяем, что заявка в статусе "Выполнена"
    if work_order.current_internal_status.short_code_en != 'completed':
        return JsonResponse({'error': 'Можно закрыть только выполненную заявку'}, status=400)

    # Закрываем заявку
    new_status = WorkOrderStatusRef.objects.get(short_code_en='closed')
    work_order.current_internal_status = new_status
    work_order.save()

    # Создаем событие
    WorkOrderEventLog.objects.create(
        work_order=work_order,
        company=work_order.company,
        department=work_order.department,
        event_type_code='closed',
        event_datetime=timezone.now(),
        text_value='Заявка закрыта',
        author_user=request.user,
        new_status=work_order.current_internal_status,
        is_visible_to_resident=True,
        is_test=False
    )

    # Записываем в историю изменений статусов
    WorkOrderStatusHistory.objects.create(
        work_order=work_order,
        status=new_status,
        changed_by=request.user,
        is_test=False
    )

    return JsonResponse({'success': True})
