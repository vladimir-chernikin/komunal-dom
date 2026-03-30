"""
Admin конфигурация для подсистемы управления заявками ЖКХ
"""
from django.contrib import admin
from django.utils.html import mark_safe
from django.db.models import Q, Count
from django.contrib.admin import SimpleListFilter

from .models import (
    RouteRef, CompanyDepartment, ContractorOrganization,
    CompanyRouteMapping, UserCompanyMembership,
    CompanyObjectServicePeriod, WorkOrderStatusRef,
    WorkOrderStatusTransition, SLAPolicy, RequestIntake,
    WorkOrder, SLAInstance, WorkOrderEventLog,
    WorkOrderAttachment, NotificationOutbox
)


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
                current_status__short_code_en__in=['completed', 'closed']
            )
        return queryset


@admin.register(RouteRef)
class RouteRefAdmin(admin.ModelAdmin):
    list_display = ['route_code', 'route_name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['route_code', 'route_name', 'description']
    ordering = ['route_code']


@admin.register(CompanyDepartment)
class CompanyDepartmentAdmin(admin.ModelAdmin):
    list_display = ['department_name', 'company', 'parent_department', 'department_code', 'is_active', 'sort_order']
    list_filter = ['company', 'is_active']
    search_fields = ['department_name', 'department_code']
    ordering = ['company', 'sort_order', 'department_name']
    autocomplete_fields = ['parent_department']


@admin.register(ContractorOrganization)
class ContractorOrganizationAdmin(admin.ModelAdmin):
    list_display = ['contractor_name', 'tax_id', 'phone', 'email', 'is_active']
    list_filter = ['is_active']
    search_fields = ['contractor_name', 'tax_id', 'email', 'phone']
    ordering = ['contractor_name']


@admin.register(CompanyRouteMapping)
class CompanyRouteMappingAdmin(admin.ModelAdmin):
    list_display = ['company', 'route', 'target_department', 'is_active']
    list_filter = ['company', 'route', 'is_active']
    search_fields = ['company__name', 'route__route_code', 'target_department__department_name']
    ordering = ['company', 'route']
    autocomplete_fields = ['company', 'route', 'target_department']


@admin.register(UserCompanyMembership)
class UserCompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'company', 'department', 'role_code', 'is_primary', 'is_active', 'date_from', 'date_to']
    list_filter = ['company', 'role_code', 'is_primary', 'is_active']
    search_fields = ['user__username', 'user__email', 'company__name', 'department__department_name']
    ordering = ['user', 'company', '-is_primary', '-is_active']
    autocomplete_fields = ['user', 'company', 'department', 'contractor_organization']


@admin.register(CompanyObjectServicePeriod)
class CompanyObjectServicePeriodAdmin(admin.ModelAdmin):
    list_display = ['object', 'company', 'date_from', 'date_to', 'is_active']
    list_filter = ['company', 'is_active']
    search_fields = ['object__service_object_id', 'company__name']
    ordering = ['object', '-date_from']
    autocomplete_fields = ['company']


@admin.register(WorkOrderStatusRef)
class WorkOrderStatusRefAdmin(admin.ModelAdmin):
    list_display = ['short_code_en', 'short_name_ru', 'display_name_for_user', 'is_terminal', 'is_active', 'sort_order']
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


@admin.register(WorkOrderStatusTransition)
class WorkOrderStatusTransitionAdmin(admin.ModelAdmin):
    list_display = ['from_status', 'to_status', 'allowed_role_code', 'is_system_transition', 'is_active']
    list_filter = ['from_status', 'to_status', 'is_system_transition', 'is_active']
    search_fields = ['allowed_role_code']
    ordering = ['from_status', 'to_status']
    autocomplete_fields = ['from_status', 'to_status']


@admin.register(SLAPolicy)
class SLAPolicyAdmin(admin.ModelAdmin):
    list_display = ['company', 'service', 'is_emergency', 'priority_code', 'calendar_type', 'is_active']
    list_filter = ['company', 'service', 'is_emergency', 'priority_code', 'calendar_type', 'is_active']
    search_fields = ['company__name', 'service__scenario_name']
    ordering = ['company', 'service', 'priority_code', 'is_emergency']
    autocomplete_fields = ['company', 'service']


@admin.register(RequestIntake)
class RequestIntakeAdmin(admin.ModelAdmin):
    list_display = ['id', 'company', 'channel_code', 'external_message_id', 'received_at', 'created_at', 'is_test']
    list_filter = ['company', 'channel_code', 'received_at', 'is_test']
    search_fields = ['external_message_id', 'message_log_ref']
    ordering = ['-received_at']
    readonly_fields = ['received_at', 'created_at', 'updated_at']
    autocomplete_fields = ['company']


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    # Кастомный шаблон для compact layout с кнопками наверх
    change_form_template = 'admin/work_orders/work_order/change_form.html'

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'work_order_no', 'company', 'object', 'service', 'route', 'department', 'responsible_user',
                'original_request_text', 'additional_info_text', 'resolution_text',
                'current_status', 'priority_code', 'is_emergency'
            )
        }),
        ('Служебное', {
            'fields': (
                'request_intake', 'resident_user', 'parent_work_order',
                'creation_source', 'created_at', 'assigned_at', 'accepted_at', 'in_progress_at',
                'resident_contacted_at', 'localized_at', 'completed_at', 'closed_at', 'cancelled_at', 'reopened_at',
                'message_log_ref', 'completed_by_user', 'closed_by_user', 'cancelled_by_user',
                'updated_at', 'is_test'
            ),
            'classes': ('collapse',),
        }),
    )

    # Убираем блок быстрых действий
    actions = None

    # Компактный список: убрали company, object, service, is_test
    list_display = ['work_order_no', 'created_at', 'department',
                   'responsible_user', 'status_display', 'priority_code',
                   'is_emergency_compact']
    list_display_links = ['work_order_no']  # Кликабельная колонка "Номер"
    list_filter = [ClosedFilter, 'company', 'department', 'current_status',
                   'priority_code', 'is_emergency', 'creation_source', 'is_test']
    search_fields = ['work_order_no', 'original_request_text', 'resolution_text']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 50  # Компактность: больше строк на странице
    autocomplete_fields = ['company', 'service', 'route', 'department',
                          'responsible_user', 'request_intake', 'resident_user',
                          'parent_work_order', 'completed_by_user', 'closed_by_user',
                          'cancelled_by_user']

    def status_display(self, obj):
        """Отображение статуса только по-русски"""
        return obj.current_status.short_name_ru if obj.current_status else '-'
    status_display.short_description = 'Статус'

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

    def get_queryset(self, request):
        """Оптимизация запросов"""
        qs = super().get_queryset(request)
        return qs.select_related(
            'company', 'object', 'service', 'department', 'responsible_user',
            'current_status'
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
                   'executor_assignment_state', 'work_start_state', 'resolution_state', 'is_test']
    list_filter = ['company', 'calendar_type', 'executor_assignment_state',
                   'work_start_state', 'resolution_state', 'is_test']
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


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ['id', 'work_order', 'recipient_user', 'event_type_code',
                   'status_code', 'created_at', 'is_test']
    list_filter = ['company', 'event_type_code', 'status_code', 'created_at', 'is_test']
    search_fields = ['work_order__work_order_no', 'event_type_code']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'processed_at', 'updated_at']
    autocomplete_fields = ['company', 'work_order', 'recipient_user']
