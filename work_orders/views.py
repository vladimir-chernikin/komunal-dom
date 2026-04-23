"""
Views для подсистемы управления заявками ЖКХ
"""
from django.views.generic import TemplateView, DetailView, CreateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q, Count, Case, When, IntegerField
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from .models import (
    WorkOrder, WorkOrderStatusRef, UserCompanyMembership,
    CompanyDepartment, WorkOrderEventLog,
    WorkOrderStatusHistory, CompanyRouteMapping
)
from portal.models import ServicesCatalog, ServiceObject, search_service_objects
from portal.mixins import get_role_dashboard_url, get_user_scope
from .forms import WorkOrderCreateForm
from .workflow import (
    ACTION_DEFINITIONS,
    WorkflowError,
    apply_action,
    build_sla_rows,
    can_close_work_order,
    can_upload_result_photo,
    create_result_photo_attachment,
    get_active_action,
    get_assignment_candidates,
    get_result_photo_attachments,
    get_user_role_codes,
)


TERMINAL_STATUS_CODES = ['completed', 'closed', 'cancelled']
COMPLETED_STATUS_CODES = ['completed', 'closed']


def _active_work_orders(queryset):
    return queryset.exclude(current_internal_status__short_code_en__in=TERMINAL_STATUS_CODES)


def _completed_work_orders(queryset):
    return queryset.filter(current_internal_status__short_code_en__in=COMPLETED_STATUS_CODES)


def _apply_status_filter(queryset, status_filter):
    if status_filter == 'active':
        return _active_work_orders(queryset)
    if status_filter == 'completed':
        return _completed_work_orders(queryset)
    if status_filter:
        return queryset.filter(current_internal_status__short_code_en=status_filter)
    return queryset


def _get_accessible_work_orders_queryset(user):
    queryset = WorkOrder.objects.filter(is_test=False).select_related(
        'company',
        'department',
        'service',
        'object',
        'responsible_user',
        'resident_user',
        'current_internal_status',
    )
    if user.is_superuser:
        return queryset
    if not user.is_authenticated:
        return queryset.none()

    scope = get_user_scope(user)
    memberships = scope['memberships']
    company_ids = scope['company_ids']
    department_ids = scope['department_ids']
    role_codes = {membership.role_code for membership in memberships}

    if memberships:
        if role_codes & {'direktor_uk', 'chief_engineer', 'django_admin', 'uk_user'}:
            return queryset.filter(company_id__in=company_ids)
        if 'executor' in role_codes:
            return queryset.filter(company_id__in=company_ids)
        if 'contractor' in role_codes:
            return queryset.filter(
                Q(responsible_user=user) |
                Q(responsible_user__isnull=True, department_id__in=department_ids)
            )
        if role_codes == {'resident'} or 'resident' in role_codes:
            return queryset.filter(resident_user=user)
        return queryset.filter(company_id__in=company_ids)

    if not user.is_staff:
        return queryset.filter(resident_user=user)

    return queryset.none()


class ExecutorDashboardView(LoginRequiredMixin, TemplateView):
    """Дашборд исполнителя с двумя табами: Мои заявки + Пул подразделения"""
    template_name = 'work_orders/executor_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем текущего пользователя
        user = self.request.user

        scope = get_user_scope(user, role_codes=['executor'])
        memberships = scope['memberships']
        primary_membership = scope['primary_membership']
        company_ids = scope['company_ids']
        hide_description_priority_columns = bool(
            primary_membership and primary_membership.role_code == 'chief_engineer'
        )
        department_ids = scope['department_ids']

        if not memberships:
            context['error'] = 'У вас нет назначенных ролей в компаниях'
            return context

        context['membership'] = primary_membership
        context['company'] = primary_membership.company
        context['department'] = primary_membership.department
        context['memberships'] = memberships

        # Мои заявки (назначенные на пользователя)
        my_requests = WorkOrder.objects.filter(
            responsible_user=user,
            company_id__in=company_ids,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')

        context['my_requests'] = my_requests

        # Статистика по моим заявкам
        context['my_requests_new'] = my_requests.filter(current_internal_status__short_code_en='accepted_by_executor').count()
        context['my_requests_in_progress'] = my_requests.filter(current_internal_status__short_code_en='in_progress').count()
        context['my_requests_on_hold'] = my_requests.filter(current_internal_status__short_code_en='on_hold').count()
        context['my_requests_completed'] = _completed_work_orders(my_requests).count()
        context['my_requests_total'] = my_requests.count()
        context['my_requests_preview'] = my_requests[:5]

        # Пул подразделения (заявки, не назначенные на исполнителя)
        pool_requests = WorkOrder.objects.filter(
            company_id__in=company_ids,
            department_id__in=department_ids,
            responsible_user__isnull=True,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')
        pool_requests = _active_work_orders(pool_requests)

        context['pool_requests'] = pool_requests

        # Статистика по пулу
        context['pool_new'] = pool_requests.filter(current_internal_status__short_code_en='new_registered').count()
        context['pool_total'] = pool_requests.count()
        context['pool_requests_preview'] = pool_requests[:5]
        all_requests = WorkOrder.objects.filter(
            company_id__in=company_ids,
            is_test=False
        )
        context['all_requests_total'] = all_requests.count()
        context['all_requests_active'] = _active_work_orders(all_requests).count()
        context['all_requests_in_progress'] = all_requests.filter(current_internal_status__short_code_en='in_progress').count()
        context['all_requests_completed'] = _completed_work_orders(all_requests).count()

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
        scope = get_user_scope(self.request.user, role_codes=['executor'])
        memberships = scope['memberships']
        primary_membership = scope['primary_membership']
        company_ids = scope['company_ids']

        if not memberships:
            context['error'] = 'У вас нет назначенных ролей исполнителя'
            return context

        my_requests = WorkOrder.objects.filter(
            responsible_user=self.request.user,
            company_id__in=company_ids,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')

        # Фильтрация по статусу
        status_filter = self.request.GET.get('status')
        if status_filter:
            my_requests = _apply_status_filter(my_requests, status_filter)

        context['my_requests'] = my_requests
        context['status_filter'] = status_filter
        context['membership'] = primary_membership
        context['company'] = primary_membership.company
        context['department'] = primary_membership.department

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

        scope = get_user_scope(self.request.user, role_codes=['executor'])
        membership = scope['primary_membership']
        company_ids = scope['company_ids']
        department_ids = scope['department_ids']

        if not membership:
            context['error'] = 'У вас нет назначенных ролей'
            return context

        # Пул заявок
        pool_requests = WorkOrder.objects.filter(
            company_id__in=company_ids,
            department_id__in=department_ids,
            responsible_user__isnull=True,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object'
        ).order_by('-created_at')
        pool_requests = _active_work_orders(pool_requests)

        context['pool_requests'] = pool_requests
        context['company'] = membership.company
        context['department'] = membership.department
        context['departments'] = [item.department for item in scope['memberships']]

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

    def get_queryset(self):
        return _get_accessible_work_orders_queryset(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # История событий
        context['sla_rows'] = build_sla_rows(self.object)
        context['active_action'] = get_active_action(self.request.user, self.object)
        context['active_action_code'] = next(
            (code for code, definition in ACTION_DEFINITIONS.items() if definition == context['active_action']),
            '',
        )
        context['can_close'] = can_close_work_order(self.request.user, self.object)
        context['close_action'] = ACTION_DEFINITIONS['close']
        context['assignment_candidates'] = get_assignment_candidates(self.object)
        context['result_photos'] = get_result_photo_attachments(self.object)
        context['result_photo_count'] = len(context['result_photos'])
        context['can_upload_result_photo'] = can_upload_result_photo(self.request.user, self.object)
        context['user_role_codes'] = sorted(get_user_role_codes(self.request.user, self.object.company_id))

        # Breadcrumbs для возврата на правильный дашборд
        dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
        context['dashboard_url'] = dashboard_url
        context['dashboard_title'] = dashboard_title

        return context


class WorkOrderCreateView(LoginRequiredMixin, CreateView):
    """Форма ручного создания заявки"""
    model = WorkOrder
    template_name = 'work_orders/work_order_create.html'
    form_class = WorkOrderCreateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse_lazy('work_orders:work_order_detail', kwargs={'work_order_id': self.object.id})

    def _get_creation_source(self, membership):
        if self.request.user.is_superuser:
            return 'manual_django_admin'

        source_by_role = {
            'direktor_uk': 'manual_director',
            'chief_engineer': 'manual_chief_engineer',
            'uk_user': 'manual_operator',
        }
        return source_by_role.get(membership.role_code, 'manual_employee')

    def _resolve_department(self, service, membership):
        service_mapping = (
            CompanyRouteMapping.objects.select_related('target_department')
            .filter(company=membership.company, service=service, is_active=True)
            .order_by('id')
            .first()
        )
        return service_mapping.target_department if service_mapping else None

    def form_valid(self, form):
        # Получаем членство пользователя
        scope = get_user_scope(self.request.user)
        membership = scope['primary_membership']

        if not membership:
            form.add_error(None, 'У вас нет назначенных ролей')
            return self.form_invalid(form)

        # Сохраняем заявку
        work_order = form.save(commit=False)
        target_department = self._resolve_department(work_order.service, membership)
        if target_department is None:
            form.add_error(
                'service',
                'Для выбранной услуги не настроен маршрут обработки по вашей компании. '
                'Настройка выполняется в разделе "Маппинги маршрутов компаний".'
            )
            return self.form_invalid(form)

        work_order.company = membership.company
        work_order.department = target_department
        work_order.creation_source = self._get_creation_source(membership)
        work_order.current_internal_status = WorkOrderStatusRef.objects.get(short_code_en='new_registered')
        work_order.created_at = timezone.now()
        work_order.is_test = False
        if membership.role_code == 'resident':
            work_order.resident_user = self.request.user
        work_order.save()
        WorkOrderStatusHistory.objects.create(
            work_order=work_order,
            status=work_order.current_internal_status,
            changed_by=self.request.user,
            is_test=False,
        )
        build_sla_rows(work_order)

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object_search_url'] = reverse_lazy('work_orders:api_service_object_search')
        context['selected_object_label'] = getattr(context['form'], 'selected_object_label', '')

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

        if self.request.user.is_superuser:
            base_work_orders = WorkOrder.objects.filter(
                is_test=False
            ).select_related(
                'current_internal_status', 'service', 'object', 'responsible_user', 'department', 'company'
            ).order_by('-created_at')
            work_orders = base_work_orders

            status_filter = self.request.GET.get('status')
            department_filter = self.request.GET.get('department')
            service_filter = self.request.GET.get('service')
            executor_filter = self.request.GET.get('executor')
            priority_filter = self.request.GET.get('priority')
            work_order_no_filter = (self.request.GET.get('work_order_no') or '').strip()
            created_date_filter = (self.request.GET.get('created_date') or '').strip()

            if work_order_no_filter:
                work_orders = work_orders.filter(work_order_no__icontains=work_order_no_filter)
            if created_date_filter:
                work_orders = work_orders.filter(created_at__date=created_date_filter)
            if status_filter:
                work_orders = _apply_status_filter(work_orders, status_filter)
            if department_filter:
                work_orders = work_orders.filter(department_id=department_filter)
            if service_filter:
                work_orders = work_orders.filter(service_id=service_filter)
            if executor_filter == 'unassigned':
                work_orders = work_orders.filter(responsible_user__isnull=True)
            elif executor_filter:
                work_orders = work_orders.filter(responsible_user_id=executor_filter)
            if priority_filter:
                work_orders = work_orders.filter(priority_code=priority_filter)

            services = list(
                base_work_orders
                .values('service_id', 'service__scenario_name')
                .order_by('service__scenario_name')
                .distinct()
            )
            responsible_users = []
            for row in (
                base_work_orders
                .filter(responsible_user__isnull=False)
                .values(
                    'responsible_user_id',
                    'responsible_user__first_name',
                    'responsible_user__last_name',
                    'responsible_user__username',
                )
                .order_by(
                    'responsible_user__last_name',
                    'responsible_user__first_name',
                    'responsible_user__username',
                )
                .distinct()
            ):
                label = ' '.join(
                    part for part in [row['responsible_user__last_name'], row['responsible_user__first_name']] if part
                ).strip() or row['responsible_user__username']
                responsible_users.append({'id': row['responsible_user_id'], 'label': label})

            context['work_orders'] = work_orders
            context['company'] = {'name': 'Все компании'}
            context['companies'] = []
            context['status_filter'] = status_filter
            context['department_filter'] = department_filter
            context['service_filter'] = service_filter
            context['executor_filter'] = executor_filter
            context['priority_filter'] = priority_filter
            context['work_order_no_filter'] = work_order_no_filter
            context['created_date_filter'] = created_date_filter
            context['hide_description_priority_columns'] = False
            context['services'] = services
            context['responsible_users'] = responsible_users
            context['departments'] = CompanyDepartment.objects.filter(is_active=True)
            dashboard_url, dashboard_title = get_role_dashboard_url(self.request.user)
            context['dashboard_url'] = dashboard_url
            context['dashboard_title'] = dashboard_title
            return context

        scope = get_user_scope(
            self.request.user,
            role_codes=['direktor_uk', 'chief_engineer', 'django_admin', 'executor'],
        )
        memberships = scope['memberships']
        primary_membership = scope['primary_membership']

        if not memberships:
            context['error'] = 'У вас нет прав для просмотра управленческого списка'
            return context

        company_ids = scope['company_ids']
        hide_description_priority_columns = bool(
            primary_membership and primary_membership.role_code == 'chief_engineer'
        )

        base_work_orders = WorkOrder.objects.filter(
            company_id__in=company_ids,
            is_test=False
        ).select_related(
            'current_internal_status', 'service', 'object', 'responsible_user', 'department'
        ).order_by('-created_at')
        work_orders = base_work_orders

        # Фильтры
        status_filter = self.request.GET.get('status')
        department_filter = self.request.GET.get('department')
        service_filter = self.request.GET.get('service')
        executor_filter = self.request.GET.get('executor')
        priority_filter = '' if hide_description_priority_columns else self.request.GET.get('priority')
        work_order_no_filter = (self.request.GET.get('work_order_no') or '').strip()
        created_date_filter = (self.request.GET.get('created_date') or '').strip()

        if work_order_no_filter:
            work_orders = work_orders.filter(work_order_no__icontains=work_order_no_filter)
        if created_date_filter:
            work_orders = work_orders.filter(created_at__date=created_date_filter)
        if status_filter:
            work_orders = _apply_status_filter(work_orders, status_filter)
        if department_filter:
            work_orders = work_orders.filter(department_id=department_filter)
        if service_filter:
            work_orders = work_orders.filter(service_id=service_filter)
        if executor_filter == 'unassigned':
            work_orders = work_orders.filter(responsible_user__isnull=True)
        elif executor_filter:
            work_orders = work_orders.filter(responsible_user_id=executor_filter)
        if priority_filter:
            work_orders = work_orders.filter(priority_code=priority_filter)

        services = list(
            base_work_orders
            .values('service_id', 'service__scenario_name')
            .order_by('service__scenario_name')
            .distinct()
        )
        responsible_users = []
        for row in (
            base_work_orders
            .filter(responsible_user__isnull=False)
            .values(
                'responsible_user_id',
                'responsible_user__first_name',
                'responsible_user__last_name',
                'responsible_user__username',
            )
            .order_by(
                'responsible_user__last_name',
                'responsible_user__first_name',
                'responsible_user__username',
            )
            .distinct()
        ):
            label = ' '.join(
                part for part in [row['responsible_user__last_name'], row['responsible_user__first_name']] if part
            ).strip() or row['responsible_user__username']
            responsible_users.append({'id': row['responsible_user_id'], 'label': label})

        context['work_orders'] = work_orders
        context['company'] = primary_membership.company
        context['companies'] = [membership.company for membership in memberships]
        context['status_filter'] = status_filter
        context['department_filter'] = department_filter
        context['service_filter'] = service_filter
        context['executor_filter'] = executor_filter
        context['priority_filter'] = priority_filter
        context['work_order_no_filter'] = work_order_no_filter
        context['created_date_filter'] = created_date_filter
        context['hide_description_priority_columns'] = hide_description_priority_columns
        context['services'] = services
        context['responsible_users'] = responsible_users

        # Список подразделений для фильтра
        context['departments'] = CompanyDepartment.objects.filter(
            company_id__in=company_ids,
            is_active=True
        )

        # Breadcrumbs для возврата на правильный дашборд
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
        all_requests = WorkOrder.objects.filter(
            resident_user=self.request.user,
            is_test=False
        ).select_related(
            'current_internal_status', 'service'
        ).order_by('-created_at')

        active_requests = _active_work_orders(all_requests)
        completed_requests = _completed_work_orders(all_requests)

        status_filter = self.request.GET.get('status', 'all')
        if status_filter == 'active':
            my_requests = active_requests
        elif status_filter == 'completed':
            my_requests = completed_requests
        else:
            status_filter = 'all'
            my_requests = all_requests

        context['my_requests'] = my_requests
        context['total_requests'] = all_requests.count()
        context['active_requests'] = active_requests.count()
        context['completed_requests'] = completed_requests.count()
        context['status_filter'] = status_filter

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
        scope = get_user_scope(user, role_codes=['contractor'])
        memberships = scope['memberships']
        primary_membership = scope['primary_membership']
        company_ids = scope['company_ids']

        if not memberships:
            context['error'] = 'У вас нет назначенных ролей подрядчика'
            return context

        # Все членства подрядчика
        context['memberships'] = memberships

        context['primary_membership'] = primary_membership
        context['company'] = primary_membership.company
        context['department'] = primary_membership.department

        # Мои заявки (назначенные на подрядчика)
        my_requests = WorkOrder.objects.filter(
            responsible_user=user,
            company_id__in=company_ids,
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


def api_service_object_search(request):
    """Адресный поиск объектов обслуживания для ручного создания заявки."""
    if not request.user.is_authenticated:
        return JsonResponse({'results': []}, status=401)

    search_term = (request.GET.get('q') or '').strip()
    if len(search_term) < 2 and not search_term.isdigit():
        return JsonResponse({'results': []})

    objects = search_service_objects(search_term, limit=20)
    return JsonResponse(
        {
            'results': [
                {
                    'id': item.service_object_id,
                    'label': item.get_search_label(),
                    'address': item.get_address_display(),
                }
                for item in objects
            ]
        }
    )


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


def _handle_action(request, work_order_id, action):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(WorkOrder, pk=work_order_id, is_test=False)

    try:
        updated_work_order = apply_action(
            work_order=work_order,
            user=request.user,
            action=action,
            resolution_text=request.POST.get('resolution_text', ''),
            responsible_user_id=request.POST.get('responsible_user_id') or None,
            force_without_photo=request.POST.get('force_without_photo') == '1',
        )
    except WorkflowError as error:
        status = 409 if error.code == 'photo_confirmation_required' else 400
        return JsonResponse(
            {
                'success': False,
                'error': error.message,
                'code': error.code,
            },
            status=status,
        )

    return JsonResponse(
        {
            'success': True,
            'work_order_id': updated_work_order.id,
            'status_code': updated_work_order.current_internal_status.short_code_en,
            'status_name': updated_work_order.current_internal_status.short_name_ru,
            'redirect_url': f'/work_orders/request/{updated_work_order.id}/',
        }
    )


@require_POST
def api_take_work_order(request, work_order_id):
    return _handle_action(request, work_order_id, 'assign')


@require_POST
def api_start_work_order(request, work_order_id):
    return _handle_action(request, work_order_id, 'start')


@require_POST
def api_localize_work_order(request, work_order_id):
    return _handle_action(request, work_order_id, 'localize')


@require_POST
def api_complete_work_order(request, work_order_id):
    return _handle_action(request, work_order_id, 'complete')


@require_POST
def api_close_work_order(request, work_order_id):
    return _handle_action(request, work_order_id, 'close')


@require_POST
def api_upload_result_photo(request, work_order_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(WorkOrder, pk=work_order_id, is_test=False)
    if not can_upload_result_photo(request.user, work_order):
        return JsonResponse({'error': 'У вас нет прав на загрузку фото по этой заявке.'}, status=403)

    uploaded_files = request.FILES.getlist('photo') or request.FILES.getlist('photos')
    if not uploaded_files:
        single_file = request.FILES.get('photo') or request.FILES.get('photos')
        if single_file is not None:
            uploaded_files = [single_file]

    if not uploaded_files:
        return JsonResponse({'error': 'Файл не передан.'}, status=400)

    allowed_types = {'image/jpeg', 'image/png', 'image/webp'}
    for uploaded_file in uploaded_files:
        if uploaded_file.content_type not in allowed_types:
            return JsonResponse({'error': 'Допустимы только JPG, PNG и WEBP.'}, status=400)
        create_result_photo_attachment(work_order, uploaded_file, request.user)

    return JsonResponse(
        {
            'success': True,
            'uploaded_count': len(uploaded_files),
            'photo_count': len(get_result_photo_attachments(work_order)),
        }
    )


def api_result_photo(request, work_order_id, attachment_id):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Не авторизован'}, status=401)

    work_order = get_object_or_404(_get_accessible_work_orders_queryset(request.user), pk=work_order_id)
    attachment_queryset = work_order.attachments.filter(
        pk=attachment_id,
        attachment_kind='result_photo',
        is_test=False,
    )

    if not can_upload_result_photo(request.user, work_order):
        attachment_queryset = attachment_queryset.filter(is_visible_to_resident=True)

    attachment = get_object_or_404(attachment_queryset)
    file_bytes = bytes(attachment.file_data or b'')
    safe_filename = (attachment.file_name or 'result-photo').replace('"', '')

    response = HttpResponse(file_bytes, content_type=attachment.mime_type or 'application/octet-stream')
    response['Content-Length'] = str(attachment.file_size or len(file_bytes))
    response['Content-Disposition'] = f'inline; filename="{safe_filename}"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


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
