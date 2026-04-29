"""
Admin конфигурация для подсистемы управления заявками ЖКХ
"""
import json
from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import mark_safe
from django.db.models import Q, Count
from django.contrib.admin import SimpleListFilter
from portal.models import ServicesCatalog

from .company_service_period_service import ServiceObjectCompanyPeriodService
from .workflow import build_sla_rows
from .models import (
    CompanyDepartment, ContractorOrganization,
    CompanyServiceRoute, UserCompanyMembership,
    CompanyObjectServicePeriod, WorkOrderStatusRef,
    SLAPolicy, WorkOrder, SLAInstance, WorkOrderEventLog,
    WorkOrderAttachment, WorkOrderStatusHistory
)


class UserCompanyMembershipAdminForm(forms.ModelForm):
    class Meta:
        model = UserCompanyMembership
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = CompanyDepartment.objects.none()

        selected_company_id = None
        if self.is_bound:
            company_value = self.data.get('company')
            if company_value:
                try:
                    selected_company_id = int(company_value)
                except (TypeError, ValueError):
                    selected_company_id = None
        elif self.instance and self.instance.pk and self.instance.company_id:
            selected_company_id = self.instance.company_id
        else:
            initial_company = self.initial.get('company')
            if initial_company:
                try:
                    selected_company_id = int(initial_company)
                except (TypeError, ValueError):
                    selected_company_id = getattr(initial_company, 'id', None)

        if selected_company_id:
            self.fields['department'].queryset = CompanyDepartment.objects.filter(
                company_id=selected_company_id,
                is_active=True,
            ).order_by('department_name')
            self.fields['department'].widget.attrs.pop('disabled', None)
        else:
            self.fields['department'].widget.attrs['disabled'] = 'disabled'

        departments_json = json.dumps(self._build_department_map(), ensure_ascii=False)
        initial_value = str(self.initial.get('department') or getattr(self.instance, 'department_id', '') or '')
        self.fields['department'].widget.attrs['data-departments-by-company'] = departments_json
        self.fields['department'].widget.attrs['data-initial-value'] = initial_value
        self.fields['department'].widget.attrs['departments_by_company_json'] = departments_json
        self.fields['department'].widget.attrs['initial_value_text'] = initial_value

    def _build_department_map(self):
        result = {}
        departments = CompanyDepartment.objects.filter(is_active=True).order_by('company__name', 'department_name')
        for department in departments:
            result.setdefault(str(department.company_id), []).append({
                'id': department.id,
                'name': f'{department.department_name} ({department.company.name})',
            })
        return result

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('company')
        department = cleaned_data.get('department')
        role_code = cleaned_data.get('role_code')
        if company and department and department.company_id != company.id:
            self.add_error('department', 'Подразделение должно принадлежать выбранной компании.')
        if department and not company:
            self.add_error('company', 'Сначала выберите компанию.')
        if role_code != 'resident' and not department:
            self.add_error('department', 'Подразделение обязательно для сотрудников.')
        return cleaned_data


class CompanyObjectServicePeriodAdminForm(forms.ModelForm):
    class Meta:
        model = CompanyObjectServicePeriod
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        service = ServiceObjectCompanyPeriodService()

        company = cleaned_data.get('company')
        service_object = cleaned_data.get('object')
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        is_active = cleaned_data.get('is_active')
        is_test = cleaned_data.get('is_test')

        if not company or not service_object or not date_from:
            return cleaned_data

        if not self.instance.pk and is_active and not is_test and date_to is None:
            service.validate_assignment_start(
                object_id=service_object.pk,
                date_from=date_from,
                is_test=is_test,
            )
            return cleaned_data

        service.validate_period(
            object_id=service_object.pk,
            company_id=company.pk,
            date_from=date_from,
            date_to=date_to,
            exclude_period_id=self.instance.pk or None,
            is_active=is_active,
            is_test=is_test,
        )
        return cleaned_data


class CompanyDepartmentAdminForm(forms.ModelForm):
    class Meta:
        model = CompanyDepartment
        fields = '__all__'

    def __init__(self, *args, request=None, selected_company=None, selected_parent_id=None, **kwargs):
        self.request = request
        self.selected_company = selected_company
        self.selected_parent_id = selected_parent_id
        super().__init__(*args, **kwargs)

        self.fields['department_code'].required = False
        self.fields['department_code'].help_text = 'Можно оставить пустым, код будет создан автоматически.'
        self.fields['department_code'].widget.attrs.setdefault('placeholder', 'Автоматически')

        company = self.selected_company or getattr(self.instance, 'company', None)
        parent_queryset = CompanyDepartment.objects.none()
        if company:
            parent_queryset = (
                CompanyDepartment.objects
                .filter(company=company)
                .select_related('parent_department')
                .order_by('department_name', 'id')
            )
            if self.instance.pk:
                parent_queryset = parent_queryset.exclude(pk=self.instance.pk)

        self.fields['parent_department'].queryset = parent_queryset
        self.fields['parent_department'].label_from_instance = self._department_label

        if not self.instance.pk and self.selected_parent_id and not self.is_bound:
            try:
                self.initial.setdefault('parent_department', int(self.selected_parent_id))
            except (TypeError, ValueError):
                pass

    def _department_label(self, department):
        ancestors = []
        parent = department.parent_department
        guard = 0
        while parent and guard < 20:
            ancestors.append(parent.department_name)
            parent = parent.parent_department
            guard += 1
        if ancestors:
            return f"{' / '.join(reversed(ancestors))} / {department.department_name}"
        return department.department_name

    def clean_parent_department(self):
        parent_department = self.cleaned_data.get('parent_department')
        company = self.selected_company or getattr(self.instance, 'company', None)
        if parent_department and company and parent_department.company_id != company.id:
            raise forms.ValidationError('Родительское подразделение должно принадлежать выбранной компании.')
        return parent_department

    def clean_department_code(self):
        department_code = (self.cleaned_data.get('department_code') or '').strip()
        if department_code:
            return department_code

        company = self.selected_company or getattr(self.instance, 'company', None)
        department_name = (self.cleaned_data.get('department_name') or '').strip()
        if company and department_name:
            return CompanyDepartment.generate_department_code(
                company_id=company.id,
                department_name=department_name,
                exclude_id=self.instance.pk,
            )
        return department_code


class CompanyServiceRouteAdminForm(forms.ModelForm):
    class Meta:
        model = CompanyServiceRoute
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_department'].queryset = CompanyDepartment.objects.none()
        self.fields['target_department'].label_from_instance = self._department_label

        selected_company_id = self._get_selected_company_id()
        if selected_company_id:
            target_department_qs = CompanyDepartment.objects.filter(
                company_id=selected_company_id,
            ).filter(
                Q(is_active=True) | Q(pk=getattr(self.instance, 'target_department_id', None))
            ).select_related('company', 'parent_department').order_by('department_name', 'id')
            self.fields['target_department'].queryset = target_department_qs
            self.fields['target_department'].widget.attrs.pop('disabled', None)
        else:
            self.fields['target_department'].widget.attrs['disabled'] = 'disabled'

        departments_json = json.dumps(self._build_department_map(), ensure_ascii=False)
        initial_value = str(self.initial.get('target_department') or getattr(self.instance, 'target_department_id', '') or '')
        self.fields['target_department'].widget.attrs['data-departments-by-company'] = departments_json
        self.fields['target_department'].widget.attrs['data-initial-value'] = initial_value
        self.fields['target_department'].widget.attrs['departments_by_company_json'] = departments_json
        self.fields['target_department'].widget.attrs['initial_value_text'] = initial_value

    def _get_selected_company_id(self):
        if self.is_bound:
            company_value = self.data.get('company')
            if company_value:
                try:
                    return int(company_value)
                except (TypeError, ValueError):
                    return None
        if self.instance and self.instance.pk and self.instance.company_id:
            return self.instance.company_id

        initial_company = self.initial.get('company')
        if initial_company:
            try:
                return int(initial_company)
            except (TypeError, ValueError):
                return getattr(initial_company, 'id', None)
        return None

    def _build_department_map(self):
        result = {}
        departments_filter = Q(is_active=True)
        if self.instance and getattr(self.instance, 'target_department_id', None):
            departments_filter |= Q(pk=self.instance.target_department_id)

        departments = (
            CompanyDepartment.objects
            .filter(departments_filter)
            .select_related('company', 'parent_department')
            .order_by('company__name', 'department_name', 'id')
        )
        for department in departments:
            result.setdefault(str(department.company_id), []).append({
                'id': department.id,
                'name': self._department_label(department),
            })
        return result

    def _department_label(self, department):
        ancestors = []
        parent = department.parent_department
        guard = 0
        while parent and guard < 20:
            ancestors.append(parent.department_name)
            parent = parent.parent_department
            guard += 1

        path_parts = list(reversed(ancestors)) + [department.department_name]
        path = ' / '.join(path_parts)
        return f'{path} ({department.company.name})'

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('company')
        service = cleaned_data.get('service')
        target_department = cleaned_data.get('target_department')
        if not service:
            self.add_error('service', 'Выберите услугу.')
        if company and target_department and target_department.company_id != company.id:
            self.add_error('target_department', 'Целевое подразделение должно принадлежать выбранной компании.')
        if target_department and not company:
            self.add_error('company', 'Сначала выберите компанию.')
        return cleaned_data


class ClosedFilter(SimpleListFilter):
    """Фильтр для показа/скрытия закрытых заявок"""
    title = 'Статус закрытия'
    parameter_name = 'show_closed'

    def lookups(self, request, model_admin):
        return (
            ('0', 'Только не закрытые'),
            ('1', 'Все включая закрытые'),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.exclude(
                current_internal_status__short_code_en__in=['completed', 'closed']
            )
        return queryset


@admin.register(CompanyDepartment)
class CompanyDepartmentAdmin(admin.ModelAdmin):
    form = CompanyDepartmentAdminForm
    change_list_template = 'admin/work_orders/company_department/change_list.html'
    change_form_template = 'admin/work_orders/company_department/change_form.html'
    list_display = ['department_tree', 'department_code', 'is_external', 'is_active']
    list_filter = []
    search_fields = ['department_name', 'department_code', 'company__name']
    ordering = ['department_name', 'id']
    readonly_fields = ['company_context']
    fieldsets = (
        ('Основное', {
                    'fields': ('company_context', 'parent_department', 'department_name', 'department_code', 'is_external', 'is_active')
        }),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                ('Основное', {
                    'fields': ('parent_department', 'department_name', 'department_code', 'is_external', 'is_active')
                }),
            )
        return super().get_fieldsets(request, obj=obj)

    def _get_primary_company(self, user):
        profile = getattr(user, 'userprofile', None)
        if profile and profile.primary_company_id:
            return profile.primary_company

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, is_active=True, date_to__isnull=True, is_primary=True)
            .select_related('company')
            .first()
        )
        if membership:
            return membership.company

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, is_active=True, date_to__isnull=True)
            .select_related('company')
            .order_by('company__name')
            .first()
        )
        if membership:
            return membership.company

        if user.is_superuser:
            from nsi.models import Company
            return Company.objects.filter(is_active=True).order_by('name', 'id').first()
        return None

    def _get_scoped_company(self, request, obj=None):
        if obj and getattr(obj, 'company_id', None):
            return obj.company
        if hasattr(request, '_company_department_scoped_company'):
            return request._company_department_scoped_company

        preferred_company = self._get_primary_company(request.user)
        if not request.user.is_superuser:
            return preferred_company

        from nsi.models import Company

        company_id = request.GET.get('company_scope') or request.POST.get('_company_scope')
        if company_id:
            try:
                company_id = int(company_id)
            except (TypeError, ValueError):
                company_id = None
        if company_id:
            company = Company.objects.filter(pk=company_id, is_active=True).first()
            if company:
                return company
        return preferred_company or Company.objects.filter(is_active=True).order_by('name', 'id').first()

    def _get_scoped_company_queryset(self, request):
        scoped_company = self._get_scoped_company(request)
        if scoped_company:
            return super().get_queryset(request).filter(company=scoped_company)
        return super().get_queryset(request).none()

    def _build_company_scope_query(self, request, company_id):
        query = request.GET.copy()
        query['company_scope'] = str(company_id)
        return query.urlencode()

    def _build_scoped_query(self, request, company_id, **extra_params):
        query = request.GET.copy()
        if company_id:
            query['company_scope'] = str(company_id)
        for key, value in extra_params.items():
            if value is None:
                query.pop(key, None)
            else:
                query[key] = str(value)
        return query.urlencode()

    def _build_department_tree_rows(self, request, queryset, scoped_company):
        departments = list(queryset)
        children_map = {}
        for department in departments:
            children_map.setdefault(department.parent_department_id, []).append(department)

        for children in children_map.values():
            children.sort(key=lambda item: (item.department_name.lower(), item.id))

        rows = []

        def walk(parent_id=None, depth=0):
            for department in children_map.get(parent_id, []):
                scope_query = self._build_company_scope_query(request, department.company_id)
                change_url = reverse('admin:work_orders_companydepartment_change', args=[department.pk])
                delete_url = reverse('admin:work_orders_companydepartment_delete', args=[department.pk])
                add_child_query = request.GET.copy()
                add_child_query['company_scope'] = str(department.company_id)
                add_child_query['parent_department'] = str(department.pk)
                rows.append({
                    'object': department,
                    'depth': depth,
                    'indent_px': depth * 28,
                    'has_children': bool(children_map.get(department.pk)),
                    'change_url': f'{change_url}?{scope_query}',
                    'delete_url': f'{delete_url}?{scope_query}',
                    'add_child_url': f"{reverse('admin:work_orders_companydepartment_add')}?{add_child_query.urlencode()}",
                })
                walk(department.pk, depth + 1)

        walk()
        return rows

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        scoped_company = self._get_scoped_company(request)
        request._company_department_scoped_company = scoped_company

        original_get = request.GET
        if 'company_scope' in request.GET:
            sanitized_get = request.GET.copy()
            sanitized_get.pop('company_scope', None)
            request.GET = sanitized_get
        try:
            response = super().changelist_view(request, extra_context=extra_context)
        finally:
            request.GET = original_get
        if not hasattr(response, 'context_data'):
            return response

        response.context_data['scoped_company'] = scoped_company
        response.context_data['department_add_root_url'] = (
            f"{reverse('admin:work_orders_companydepartment_add')}?{self._build_company_scope_query(request, scoped_company.pk)}"
            if scoped_company else reverse('admin:work_orders_companydepartment_add')
        )
        response.context_data['department_changelist_base_url'] = reverse('admin:work_orders_companydepartment_changelist')

        changelist = response.context_data.get('cl')
        filtered_queryset = changelist.queryset if changelist is not None else self.get_queryset(request)
        response.context_data['department_tree_rows'] = self._build_department_tree_rows(
            request,
            filtered_queryset.select_related('company', 'parent_department'),
            scoped_company,
        )

        if request.user.is_superuser:
            from nsi.models import Company
            response.context_data['company_scope_options'] = Company.objects.filter(is_active=True).order_by('name', 'id')

        return response

    def get_queryset(self, request):
        qs = self._get_scoped_company_queryset(request)
        return qs.select_related('company', 'parent_department')

    def lookup_allowed(self, lookup, value, request):
        if lookup == 'company_scope':
            return True
        return super().lookup_allowed(lookup, value, request)

    def get_form(self, request, obj=None, change=False, **kwargs):
        base_form = super().get_form(request, obj, change=change, **kwargs)
        selected_company = self._get_scoped_company(request, obj=obj)
        selected_parent_id = request.GET.get('parent_department')

        class RequestAwareCompanyDepartmentForm(base_form):
            def __init__(self, *args, **inner_kwargs):
                inner_kwargs['request'] = request
                inner_kwargs['selected_company'] = selected_company
                inner_kwargs['selected_parent_id'] = selected_parent_id
                super().__init__(*args, **inner_kwargs)

        return RequestAwareCompanyDepartmentForm

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        parent_department = request.GET.get('parent_department')
        if parent_department:
            initial['parent_department'] = parent_department
        return initial

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        scoped_company = self._get_scoped_company(request, obj=obj)
        query = request.GET.copy()
        if scoped_company:
            query['company_scope'] = str(scoped_company.pk)
        parent_department = getattr(obj, 'parent_department', None)
        if parent_department is None:
            parent_department_id = request.GET.get('parent_department')
            if parent_department_id:
                try:
                    parent_department = CompanyDepartment.objects.filter(
                        pk=int(parent_department_id),
                        company=scoped_company,
                    ).first()
                except (TypeError, ValueError):
                    parent_department = None
        context['department_context_company'] = scoped_company or getattr(obj, 'company', None)
        context['department_context_parent'] = parent_department
        context['department_changelist_url'] = (
            f"{reverse('admin:work_orders_companydepartment_changelist')}?{query.urlencode()}"
            if query else reverse('admin:work_orders_companydepartment_changelist')
        )
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)

    def save_model(self, request, obj, form, change):
        if not change and not obj.company_id:
            scoped_company = self._get_scoped_company(request)
            if scoped_company:
                obj.company = scoped_company
        super().save_model(request, obj, form, change)

    def department_tree(self, obj):
        ancestors = []
        parent = obj.parent_department
        guard = 0
        while parent and guard < 20:
            ancestors.append(parent.department_name)
            parent = parent.parent_department
            guard += 1

        depth = len(ancestors)
        indent = '&nbsp;' * (depth * 6)
        branch = '└─ ' if depth else ''
        parent_path = ' / '.join(reversed(ancestors))

        html = f'<strong>{indent}{branch}{obj.department_name}</strong>'
        if parent_path:
            html += f'<div style="font-size: 12px; color: #6c757d;">Подчинение: {parent_path}</div>'
        return mark_safe(html)
    department_tree.short_description = 'Подразделение / дерево'
    department_tree.admin_order_field = 'department_name'

    def company_context(self, obj):
        company = getattr(obj, 'company', None)
        if company:
            return company.name
        return '-'
    company_context.short_description = 'Компания'

    def get_search_results(self, request, queryset, search_term):
        """
        Переопределенный поиск для поддержки фильтрации по company_id
        в autocomplete запросах из UserCompanyMembershipInline
        """
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        # Фильтрация по company_id для autocomplete в UserCompanyMembershipInline
        company_id = request.GET.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        return queryset, use_distinct


@admin.register(ContractorOrganization)
class ContractorOrganizationAdmin(admin.ModelAdmin):
    list_display = ['contractor_name', 'tax_id', 'phone', 'email', 'is_active']
    list_filter = ['is_active']
    search_fields = ['contractor_name', 'tax_id', 'email', 'phone']
    ordering = ['contractor_name']


@admin.register(CompanyServiceRoute)
class CompanyServiceRouteAdmin(admin.ModelAdmin):
    form = CompanyServiceRouteAdminForm
    change_list_template = 'admin/work_orders/companyserviceroute/change_list.html'
    change_form_template = 'admin/work_orders/companyserviceroute/change_form.html'
    fields = ['company', 'service', 'target_department', 'is_active', 'is_test']
    list_display = ['company', 'service', 'target_department', 'is_active']
    list_filter = []
    search_fields = ['company__name', 'service__scenario_name', 'service__category_name', 'target_department__department_name']
    ordering = ['company__name', 'service__category_name', 'service__scenario_name', 'id']
    autocomplete_fields = ['company']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'fill-by-company/',
                self.admin_site.admin_view(self.fill_by_company_view),
                name='work_orders_companyserviceroute_fill_by_company',
            ),
        ]
        return custom_urls + urls

    def _get_primary_company(self, user):
        profile = getattr(user, 'userprofile', None)
        if profile and profile.primary_company_id:
            return profile.primary_company

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, is_active=True, date_to__isnull=True, is_primary=True)
            .select_related('company')
            .first()
        )
        if membership:
            return membership.company

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, is_active=True, date_to__isnull=True)
            .select_related('company')
            .order_by('company__name')
            .first()
        )
        if membership:
            return membership.company

        if user.is_superuser:
            from nsi.models import Company
            return Company.objects.filter(is_active=True).order_by('name', 'id').first()
        return None

    def _get_company_scope_options(self, request):
        from nsi.models import Company
        if request.user.is_superuser:
            return Company.objects.filter(is_active=True).order_by('name', 'id')

        company_ids = set(
            UserCompanyMembership.objects
            .filter(user=request.user, is_active=True, date_to__isnull=True)
            .values_list('company_id', flat=True)
        )
        profile = getattr(request.user, 'userprofile', None)
        if profile and profile.primary_company_id:
            company_ids.add(profile.primary_company_id)
        return Company.objects.filter(is_active=True, pk__in=company_ids).order_by('name', 'id')

    def _get_scoped_company(self, request, obj=None):
        if obj and getattr(obj, 'company_id', None):
            return obj.company
        if hasattr(request, '_company_service_route_scoped_company'):
            return request._company_service_route_scoped_company

        company_id = request.GET.get('company_scope') or request.POST.get('_company_scope')
        try:
            company_id = int(company_id) if company_id else None
        except (TypeError, ValueError):
            company_id = None

        allowed_companies = self._get_company_scope_options(request)
        if company_id:
            company = allowed_companies.filter(pk=company_id).first()
            if company:
                return company

        return self._get_primary_company(request.user) or allowed_companies.first()

    def _build_company_scope_query(self, request, company_id):
        query = request.GET.copy()
        query['company_scope'] = str(company_id)
        return query.urlencode()

    def _department_label(self, department):
        ancestors = []
        parent = department.parent_department
        guard = 0
        while parent and guard < 20:
            ancestors.append(parent.department_name)
            parent = parent.parent_department
            guard += 1

        path_parts = list(reversed(ancestors)) + [department.department_name]
        return ' / '.join(path_parts)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related('company', 'service', 'target_department')
        scoped_company = self._get_scoped_company(request)
        request._company_service_route_scoped_company = scoped_company
        if scoped_company:
            return queryset.filter(company=scoped_company)
        return queryset.none()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        scoped_company = self._get_scoped_company(request)
        request._company_service_route_scoped_company = scoped_company

        original_get = request.GET
        if 'company_scope' in request.GET:
            sanitized_get = request.GET.copy()
            sanitized_get.pop('company_scope', None)
            request.GET = sanitized_get
        try:
            response = super().changelist_view(request, extra_context=extra_context)
        finally:
            request.GET = original_get
        if not hasattr(response, 'context_data'):
            return response

        base_url = reverse('admin:work_orders_companyserviceroute_changelist')
        fill_url = reverse('admin:work_orders_companyserviceroute_fill_by_company')
        response.context_data['scoped_company'] = scoped_company
        response.context_data['company_scope_options'] = self._get_company_scope_options(request)
        response.context_data['company_service_route_base_url'] = base_url
        response.context_data['company_service_route_fill_url'] = fill_url
        response.context_data['company_service_route_add_url'] = (
            f"{reverse('admin:work_orders_companyserviceroute_add')}?{self._build_company_scope_query(request, scoped_company.pk)}"
            if scoped_company else reverse('admin:work_orders_companyserviceroute_add')
        )
        return response

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        company = self._get_scoped_company(request)
        if company:
            initial['company'] = company.pk
        return initial

    def fill_by_company_view(self, request):
        scoped_company = self._get_scoped_company(request)
        request._company_service_route_scoped_company = scoped_company
        if not scoped_company:
            self.message_user(request, 'Не удалось определить компанию для заполнения маршрутов.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:work_orders_companyserviceroute_changelist'))

        services = list(
            ServicesCatalog.objects
            .filter(is_active=True)
            .select_related('category')
            .order_by('category_id', 'scenario_name', 'service_id')
        )
        mappings = {
            mapping.service_id: mapping
            for mapping in CompanyServiceRoute.objects
            .filter(company=scoped_company)
            .exclude(service__isnull=True)
            .select_related('service', 'target_department')
        }

        department_filter = Q(is_active=True)
        existing_department_ids = [
            mapping.target_department_id for mapping in mappings.values()
            if mapping.target_department_id
        ]
        if existing_department_ids:
            department_filter |= Q(pk__in=existing_department_ids)
        departments = list(
            CompanyDepartment.objects
            .filter(company=scoped_company)
            .filter(department_filter)
            .select_related('parent_department')
            .order_by('parent_department_id', 'department_name', 'id')
        )
        department_ids = {department.pk for department in departments}

        if request.method == 'POST':
            errors = []
            to_create = []
            to_update = []

            for service in services:
                mapping = mappings.get(service.pk)
                raw_department_id = (request.POST.get(f'target_department_{service.pk}') or '').strip()
                is_active = request.POST.get(f'is_active_{service.pk}') == 'on'

                if not raw_department_id:
                    if mapping:
                        continue
                    continue

                try:
                    department_id = int(raw_department_id)
                except (TypeError, ValueError):
                    errors.append(f'Некорректное подразделение для услуги {service}.')
                    continue

                if department_id not in department_ids:
                    errors.append(f'Подразделение для услуги {service} не принадлежит выбранной компании.')
                    continue

                if mapping:
                    if mapping.target_department_id != department_id or mapping.is_active != is_active:
                        mapping.target_department_id = department_id
                        mapping.is_active = is_active
                        to_update.append(mapping)
                else:
                    to_create.append(CompanyServiceRoute(
                        company=scoped_company,
                        service=service,
                        target_department_id=department_id,
                        is_active=is_active,
                    ))

            if errors:
                for error in errors:
                    self.message_user(request, error, level=messages.ERROR)
            else:
                with transaction.atomic():
                    if to_create:
                        CompanyServiceRoute.objects.bulk_create(to_create)
                    for mapping in to_update:
                        mapping.save(update_fields=['target_department', 'is_active', 'updated_at'])

                self.message_user(
                    request,
                    f'Маршруты услуг по компании сохранены. Создано: {len(to_create)}, обновлено: {len(to_update)}.',
                    level=messages.SUCCESS,
                )
                return HttpResponseRedirect(
                    f"{reverse('admin:work_orders_companyserviceroute_changelist')}?company_scope={scoped_company.pk}"
                )

        rows = []
        posted = request.method == 'POST'
        for service in services:
            mapping = mappings.get(service.pk)
            posted_department_id = request.POST.get(f'target_department_{service.pk}') if posted else None
            selected_department_id = (
                posted_department_id
                if posted_department_id is not None
                else str(mapping.target_department_id) if mapping else ''
            )
            rows.append({
                'service': service,
                'mapping': mapping,
                'selected_department_id': str(selected_department_id or ''),
                'is_active': (
                    request.POST.get(f'is_active_{service.pk}') == 'on'
                    if posted else mapping.is_active if mapping else True
                ),
            })

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Заполнить маршруты услуг: {scoped_company.name}',
            'scoped_company': scoped_company,
            'services': services,
            'rows': rows,
            'departments': departments,
            'changelist_url': f"{reverse('admin:work_orders_companyserviceroute_changelist')}?company_scope={scoped_company.pk}",
            'has_change_permission': self.has_change_permission(request),
        }
        return TemplateResponse(
            request,
            'admin/work_orders/companyserviceroute/fill_by_company.html',
            context,
        )

@admin.register(UserCompanyMembership)
class UserCompanyMembershipAdmin(admin.ModelAdmin):
    form = UserCompanyMembershipAdminForm
    change_form_template = 'admin/work_orders/usercompanymembership/change_form.html'
    list_display = ['user', 'company', 'department', 'role_code', 'is_primary', 'is_active', 'date_from', 'date_to']
    list_filter = ['company', 'role_code', 'is_primary', 'is_active']
    search_fields = ['user__username', 'user__email', 'company__name', 'department__department_name']
    ordering = ['user', 'company', '-is_primary', '-is_active']
    autocomplete_fields = ['user', 'contractor_organization']

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        user_id = request.GET.get('user')
        if user_id:
            initial['user'] = user_id
        return initial


@admin.register(CompanyObjectServicePeriod)
class CompanyObjectServicePeriodAdmin(admin.ModelAdmin):
    form = CompanyObjectServicePeriodAdminForm
    list_display = ['object', 'company', 'date_from', 'date_to', 'is_active']
    list_filter = ['company', 'is_active']
    search_fields = ['object__service_object_id', 'company__name']
    ordering = ['object', '-date_from']
    autocomplete_fields = ['company']

    def save_model(self, request, obj, form, change):
        if not change and obj.is_active and not obj.is_test and obj.date_to is None:
            service = ServiceObjectCompanyPeriodService()
            result = service.assign_company(
                object_id=obj.object_id,
                company_id=obj.company_id,
                date_from=obj.date_from,
                comment=obj.comment,
                is_test=obj.is_test,
            )
            obj.pk = result.period.pk
            obj.id = result.period.pk
            if result.previous_period is not None:
                self.message_user(
                    request,
                    (
                        f'Предыдущий открытый период для объекта {obj.object_id} '
                        f'закрыт датой {result.previous_period.date_to}.'
                    ),
                    level=messages.INFO,
                )
            return
        super().save_model(request, obj, form, change)


@admin.register(WorkOrderStatusRef)
class WorkOrderStatusRefAdmin(admin.ModelAdmin):
    list_display = ['short_code_en', 'short_name_ru', 'display_name_for_user', 'is_terminal', 'is_active', 'sort_order']
    list_display_links = ['short_code_en', 'short_name_ru', 'display_name_for_user']  # Первые 3 колонки кликабельные
    list_filter = ['is_terminal', 'is_active']
    search_fields = ['short_code_en', 'short_name_ru', 'display_name_for_user', 'description_and_transition_rules']
    ordering = ['sort_order', 'short_code_en']
    fieldsets = (
        ('Основное', {
            'fields': ('short_code_en', 'short_name_ru', 'display_name_for_user')
        }),
        ('Дополнительно', {
            'fields': ('description_and_transition_rules', 'sort_order', 'is_terminal', 'is_active')
        }),
    )


@admin.register(SLAPolicy)
class SLAPolicyAdmin(admin.ModelAdmin):
    change_list_template = 'admin/work_orders/slapolicy/change_list.html'
    list_display = [
        'company', 'service', 'calendar_type',
        'reaction_minutes', 'localization_minutes', 'completion_minutes',
        'is_active', 'is_test',
    ]
    list_filter = []
    search_fields = ['company__name', 'service__scenario_name']
    ordering = ['company', 'service', 'calendar_type']
    autocomplete_fields = ['company', 'service']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'fill-by-company/',
                self.admin_site.admin_view(self.fill_by_company_view),
                name='work_orders_slapolicy_fill_by_company',
            ),
        ]
        return custom_urls + urls

    def _get_primary_company(self, user):
        profile = getattr(user, 'userprofile', None)
        if profile and profile.primary_company_id:
            return profile.primary_company

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, is_active=True, date_to__isnull=True, is_primary=True)
            .select_related('company')
            .first()
        )
        if membership:
            return membership.company

        membership = (
            UserCompanyMembership.objects
            .filter(user=user, is_active=True, date_to__isnull=True)
            .select_related('company')
            .order_by('company__name')
            .first()
        )
        if membership:
            return membership.company

        if user.is_superuser:
            from nsi.models import Company
            return Company.objects.filter(is_active=True).order_by('name', 'id').first()
        return None

    def _get_company_scope_options(self, request):
        from nsi.models import Company
        if request.user.is_superuser:
            return Company.objects.filter(is_active=True).order_by('name', 'id')

        company_ids = set(
            UserCompanyMembership.objects
            .filter(user=request.user, is_active=True, date_to__isnull=True)
            .values_list('company_id', flat=True)
        )
        profile = getattr(request.user, 'userprofile', None)
        if profile and profile.primary_company_id:
            company_ids.add(profile.primary_company_id)
        return Company.objects.filter(is_active=True, pk__in=company_ids).order_by('name', 'id')

    def _get_scoped_company(self, request, obj=None):
        if obj and getattr(obj, 'company_id', None):
            return obj.company
        if hasattr(request, '_sla_policy_scoped_company'):
            return request._sla_policy_scoped_company

        company_id = request.GET.get('company_scope') or request.POST.get('_company_scope')
        try:
            company_id = int(company_id) if company_id else None
        except (TypeError, ValueError):
            company_id = None

        allowed_companies = self._get_company_scope_options(request)
        if company_id:
            company = allowed_companies.filter(pk=company_id).first()
            if company:
                return company

        return self._get_primary_company(request.user) or allowed_companies.first()

    def _build_company_scope_query(self, request, company_id):
        query = request.GET.copy()
        query['company_scope'] = str(company_id)
        return query.urlencode()

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related('company', 'service')
        scoped_company = self._get_scoped_company(request)
        request._sla_policy_scoped_company = scoped_company
        if scoped_company:
            return queryset.filter(company=scoped_company)
        return queryset.none()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        scoped_company = self._get_scoped_company(request)
        request._sla_policy_scoped_company = scoped_company

        original_get = request.GET
        if 'company_scope' in request.GET:
            sanitized_get = request.GET.copy()
            sanitized_get.pop('company_scope', None)
            request.GET = sanitized_get
        try:
            response = super().changelist_view(request, extra_context=extra_context)
        finally:
            request.GET = original_get
        if not hasattr(response, 'context_data'):
            return response

        response.context_data['scoped_company'] = scoped_company
        response.context_data['company_scope_options'] = self._get_company_scope_options(request)
        response.context_data['sla_policy_base_url'] = reverse('admin:work_orders_slapolicy_changelist')
        response.context_data['sla_policy_fill_url'] = reverse('admin:work_orders_slapolicy_fill_by_company')
        response.context_data['sla_policy_add_url'] = (
            f"{reverse('admin:work_orders_slapolicy_add')}?{self._build_company_scope_query(request, scoped_company.pk)}"
            if scoped_company else reverse('admin:work_orders_slapolicy_add')
        )
        return response

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        company = self._get_scoped_company(request)
        if company:
            initial['company'] = company.pk
        initial.setdefault('calendar_type', '24x7')
        initial.setdefault('is_active', True)
        initial.setdefault('is_test', False)
        return initial

    def fill_by_company_view(self, request):
        scoped_company = self._get_scoped_company(request)
        request._sla_policy_scoped_company = scoped_company
        if not scoped_company:
            self.message_user(request, 'Не удалось определить компанию для заполнения SLA.', level=messages.ERROR)
            return HttpResponseRedirect(reverse('admin:work_orders_slapolicy_changelist'))

        services = list(ServicesCatalog.objects.filter(is_active=True).order_by('category_name', 'scenario_name', 'service_id'))
        policies = {
            policy.service_id: policy
            for policy in SLAPolicy.objects
            .filter(company=scoped_company, is_active=True)
            .select_related('service')
        }

        if request.method == 'POST':
            errors = []
            to_create = []
            to_update = []

            for service in services:
                policy = policies.get(service.pk)
                raw_values = {
                    'reaction_minutes': (request.POST.get(f'reaction_minutes_{service.pk}') or '').strip(),
                    'localization_minutes': (request.POST.get(f'localization_minutes_{service.pk}') or '').strip(),
                    'completion_minutes': (request.POST.get(f'completion_minutes_{service.pk}') or '').strip(),
                }
                if not all(raw_values.values()):
                    errors.append(f'Заполните все 3 SLA-значения для услуги "{service.scenario_name}".')
                    continue

                parsed_values = {}
                for field_name, raw_value in raw_values.items():
                    try:
                        value = int(raw_value)
                    except (TypeError, ValueError):
                        errors.append(f'Поле {field_name} для услуги "{service.scenario_name}" должно быть числом.')
                        continue
                    if value < 0:
                        errors.append(f'Поле {field_name} для услуги "{service.scenario_name}" не может быть отрицательным.')
                        continue
                    parsed_values[field_name] = value

                if len(parsed_values) != 3:
                    continue

                if policy:
                    changed = False
                    for field_name, value in parsed_values.items():
                        if getattr(policy, field_name) != value:
                            setattr(policy, field_name, value)
                            changed = True
                    if changed:
                        to_update.append(policy)
                else:
                    to_create.append(SLAPolicy(
                        company=scoped_company,
                        service=service,
                        calendar_type='24x7',
                        reaction_minutes=parsed_values['reaction_minutes'],
                        localization_minutes=parsed_values['localization_minutes'],
                        completion_minutes=parsed_values['completion_minutes'],
                        is_active=True,
                        is_test=False,
                    ))

            if errors:
                for error in errors:
                    self.message_user(request, error, level=messages.ERROR)
            else:
                with transaction.atomic():
                    if to_create:
                        SLAPolicy.objects.bulk_create(to_create)
                    for policy in to_update:
                        policy.save(update_fields=[
                            'reaction_minutes',
                            'localization_minutes',
                            'completion_minutes',
                            'updated_at',
                        ])

                self.message_user(
                    request,
                    f'SLA по компании сохранены. Создано: {len(to_create)}, обновлено: {len(to_update)}.',
                    level=messages.SUCCESS,
                )
                return HttpResponseRedirect(
                    f"{reverse('admin:work_orders_slapolicy_changelist')}?company_scope={scoped_company.pk}"
                )

        rows = []
        posted = request.method == 'POST'
        for service in services:
            policy = policies.get(service.pk)
            rows.append({
                'service': service,
                'policy': policy,
                'reaction_minutes': (
                    request.POST.get(f'reaction_minutes_{service.pk}')
                    if posted else policy.reaction_minutes if policy else ''
                ),
                'localization_minutes': (
                    request.POST.get(f'localization_minutes_{service.pk}')
                    if posted else policy.localization_minutes if policy else ''
                ),
                'completion_minutes': (
                    request.POST.get(f'completion_minutes_{service.pk}')
                    if posted else policy.completion_minutes if policy else ''
                ),
            })

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Заполнить SLA: {scoped_company.name}',
            'scoped_company': scoped_company,
            'rows': rows,
            'changelist_url': f"{reverse('admin:work_orders_slapolicy_changelist')}?company_scope={scoped_company.pk}",
            'has_change_permission': self.has_change_permission(request),
        }
        return TemplateResponse(
            request,
            'admin/work_orders/slapolicy/fill_by_company.html',
            context,
        )


class WorkOrderStatusHistoryInline(admin.TabularInline):
    """Inline для истории изменения статусов (readonly)"""
    model = WorkOrderStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ['changed_at_display', 'status_display', 'changed_by_display']
    fields = ['changed_at_display', 'status_display', 'changed_by_display']

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changed_at_display(self, obj):
        """Форматированное отображение даты изменения"""
        from django.utils import timezone
        if obj.changed_at:
            local_time = timezone.localtime(obj.changed_at)
            return local_time.strftime('%d.%m.%Y %H:%M:%S')
        return '-'
    changed_at_display.short_description = 'Дата и время'

    def status_display(self, obj):
        """Отображение статуса"""
        return obj.status.short_name_ru if obj.status else '-'
    status_display.short_description = 'Статус'

    def changed_by_display(self, obj):
        """Отображение пользователя"""
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.username
        return '-'
    changed_by_display.short_description = 'Кто изменил'


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    # Кастомный шаблон для compact layout с кнопками наверх
    change_form_template = 'admin/work_orders/work_order/change_form.html'

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'work_order_no', 'created_at', 'company', 'object', 'object_link', 'service', 'department', 'responsible_user',
                'original_request_text', 'additional_info_text', 'resolution_text',
                'current_internal_status', 'priority_code', 'is_emergency'
            )
        }),
        ('Служебное', {
            'fields': (
                'resident_user', 'parent_work_order',
                'creation_source', 'message_log_ref', 'is_test'
            ),
            'classes': ('collapse',),
        }),
    )

    # Убираем блок быстрых действий
    actions = None

    # Компактный список: убрали company, object, service, is_test
    list_display = ['work_order_with_date', 'department',
                   'responsible_user', 'status_display', 'priority_code',
                   'is_emergency_compact']
    list_display_links = ['work_order_with_date']  # Кликабельная вся ячейка, но внутри просто текст
    list_filter = [ClosedFilter, 'company', 'department', 'current_internal_status',
                   'priority_code', 'is_emergency', 'creation_source', 'is_test']
    search_fields = ['work_order_no', 'original_request_text', 'resolution_text']
    ordering = ['-created_at']
    readonly_fields = ['work_order_no', 'created_at', 'object_link']
    raw_id_fields = ['object']
    list_per_page = 50  # Компактность: больше строк на странице
    autocomplete_fields = ['company', 'service', 'department',
                          'responsible_user', 'resident_user',
                          'parent_work_order']
    inlines = [WorkOrderStatusHistoryInline]  # История изменения статусов на закладке "Служебное"

    def status_display(self, obj):
        """Отображение статуса только по-русски"""
        return obj.current_internal_status.short_name_ru if obj.current_internal_status else '-'
    status_display.short_description = 'Статус'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        work_order = self.get_object(request, object_id)
        extra_context['sla_rows'] = build_sla_rows(work_order) if work_order else []
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def responsible_user(self, obj):
        """Компактное отображение исполнителя"""
        if obj.responsible_user:
            return obj.responsible_user.get_full_name() or obj.responsible_user.username
        return mark_safe('<span class="text-muted">Не назначен</span>')
    responsible_user.short_description = 'Исполнитель'

    def is_emergency_compact(self, obj):
        """Компактное отображение аварийности"""
        if obj.is_emergency:
            return mark_safe('<span class="badge bg-danger">Авария</span>')
        return mark_safe('<span class="text-muted">-</span>')
    is_emergency_compact.short_description = 'Авария'
    is_emergency_compact.admin_order_field = 'is_emergency'

    def work_order_with_date(self, obj):
        """Объединенное отображение номера и даты создания в одну строку"""
        from django.utils import timezone
        # Форматируем дату
        if obj.created_at:
            # Локализуем дату
            local_time = timezone.localtime(obj.created_at)
            date_str = local_time.strftime('%d.%m.%Y %H:%M')
        else:
            date_str = '-'

        # Возвращаем простой текст с разделителем (Django обернет в <a>)
        return f'{obj.work_order_no}  |  {date_str}'
    work_order_with_date.short_description = 'Заявка'

    def object_link(self, obj):
        """Ссылка на просмотр объекта обслуживания"""
        if obj and getattr(obj, 'object_id', None):
            from django.urls import reverse
            from urllib.parse import quote
            url = reverse('admin:portal_serviceobject_change', args=[obj.object.id])
            return mark_safe(
                f'<a href="{url}" class="button" style="display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; font-size: 12px;">'
                f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                f'<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>'
                f'<circle cx="12" cy="12" r="3"></circle></svg>'
                f'Просмотр объекта</a>'
            )
        return '-'
    object_link.short_description = 'Объект обслуживания'

    def get_queryset(self, request):
        """Оптимизация запросов"""
        qs = super().get_queryset(request)
        return qs.select_related(
            'company', 'object', 'service', 'department', 'responsible_user',
            'current_internal_status'
        )

    def get_list_filter(self, request):
        """Скрываем фильтры от обычных пользователей, но оставляем ClosedFilter"""
        filters = super().get_list_filter(request)

        # ClosedFilter показываем всегда
        closed_filter = ClosedFilter
        other_filters = [f for f in filters if f != ClosedFilter]

        # Проверяем роль пользователя
        if request.user.is_superuser:
            return filters

        # Проверяем membership с нужными ролями
        from .models import UserCompanyMembership
        has_access = UserCompanyMembership.objects.filter(
            user=request.user,
            role_code__in=['django_admin', 'direktor_uk', 'chief_engineer'],
            is_active=True
        ).exists()

        if has_access:
            return filters
        else:
            # Обычным пользователям показываем только ClosedFilter
            return [closed_filter]


@admin.register(SLAInstance)
class SLAInstanceAdmin(admin.ModelAdmin):
    list_display = ['id', 'work_order', 'company', 'calendar_type',
                   'reaction_state', 'localization_state', 'completion_state', 'is_test']
    list_filter = ['company', 'calendar_type', 'reaction_state',
                   'localization_state', 'completion_state', 'is_test']
    search_fields = ['work_order__work_order_no']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['work_order', 'company', 'sla_policy']


@admin.register(WorkOrderEventLog)
class WorkOrderEventLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'work_order', 'event_type_code', 'event_datetime',
                   'author_user', 'is_visible_to_resident', 'created_at']
    list_filter = ['company', 'department', 'event_type_code', 'is_visible_to_resident',
                   'event_datetime', 'is_test']
    search_fields = ['work_order__work_order_no', 'event_type_code', 'text_value']
    ordering = ['-event_datetime']
    readonly_fields = ['event_datetime', 'created_at', 'updated_at']
    autocomplete_fields = ['work_order', 'company', 'department', 'author_user',
                          'old_status', 'new_status', 'old_service', 'new_service',
                          'old_responsible_user', 'new_responsible_user']


@admin.register(WorkOrderAttachment)
class WorkOrderAttachmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'work_order', 'attachment_kind', 'file_name', 'file_size',
                   'uploaded_by_user', 'is_visible_to_resident', 'uploaded_at', 'is_test']
    list_filter = ['attachment_kind', 'is_visible_to_resident', 'is_test']
    search_fields = ['file_name', 'work_order__work_order_no']
    ordering = ['-uploaded_at']
    readonly_fields = ['uploaded_at', 'created_at', 'updated_at']
    autocomplete_fields = ['work_order', 'event', 'uploaded_by_user']
