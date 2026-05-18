from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import render
from django.http import HttpResponseRedirect
from .models import UserProfile, AIPrompt, SemanticPattern, ServicesCatalog, ServiceObject, search_service_objects
from .forms import UserAdminAddForm, UserAdminChangeForm
from nsi.models import RefCategory
from work_orders.models import UserCompanyMembership


# ============================================
# Inline для UserCompanyMembership
# ============================================

class UserCompanyMembershipInline(admin.TabularInline):
    """
    Inline для отображения членств пользователя в компаниях

    ПОКАЗЫВАЕТСЯ внизу формы пользователя
    """
    model = UserCompanyMembership
    verbose_name_plural = 'Членства в компаниях'
    extra = 0
    can_delete = False
    show_change_link = False
    classes = ('user-membership-inline',)
    fields = (
        'company_display',
        'department_display',
        'role_display',
        'primary_display',
        'active_display',
        'date_from',
        'date_to',
    )
    readonly_fields = fields

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('company', 'department').order_by('-is_primary', 'company__name')

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def get_formset(self, request, obj=None, **kwargs):
        self.verbose_name_plural = 'Членства в компаниях'
        add_url = reverse('admin:work_orders_usercompanymembership_add')
        if obj and obj.pk:
            add_url = f'{add_url}?user={obj.pk}'
        self.verbose_name_plural = mark_safe(
            f'Членства в компаниях <a href="{add_url}" class="button" style="margin-left: 12px;">+ Добавить</a>'
        )
        return super().get_formset(request, obj, **kwargs)

    def company_display(self, obj):
        return obj.company.name if obj.company else '-'
    company_display.short_description = 'Компания'

    def department_display(self, obj):
        return obj.department.department_name if obj.department else '-'
    department_display.short_description = 'Подразделение'

    def role_display(self, obj):
        return obj.get_role_code_display()
    role_display.short_description = 'Роль'

    def primary_display(self, obj):
        return 'Да' if obj.is_primary else 'Нет'
    primary_display.short_description = 'Основная привязка'

    def active_display(self, obj):
        return 'Да' if obj.is_active else 'Нет'
    active_display.short_description = 'Активен'


# Отключаем стандартную регистрацию User
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Красивый интерфейс редактирования пользователя

    ИЗМЕНЕНО (2026-04-02):
    - Добавлена ссылка на компанию из UserCompanyMembership
    - get_role() использует UserCompanyMembership
    - Добавлены timezone и phone в основную информацию
    """

    list_display = ('username', 'email', 'first_name', 'last_name', 'get_company', 'get_role', 'is_active', 'date_joined')
    add_form = UserAdminAddForm
    form = UserAdminChangeForm
    add_form_template = 'admin/portal/user/change_form.html'
    change_form_template = 'admin/portal/user/change_form.html'
    change_list_template = 'admin/auth/user/change_list.html'
    inlines = [UserCompanyMembershipInline]
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    save_on_top = True

    fieldsets = (
        ('Основная информация', {
            'fields': (
                'username', 'password', 'first_name', 'last_name', 'email',
                'is_active', 'is_staff',
                'primary_company', 'primary_department', 'profile_job_title',
                'get_phone', 'get_address', 'get_timezone',
                'get_specialization', 'get_responsibilities',
            ),
            'classes': ('wide',),
        }),
        ('Права доступа', {
            'fields': ('is_superuser', 'groups', 'user_permissions'),
            'classes': ('wide',),
            'description': mark_safe('<strong>ВНИМАНИЕ:</strong> is_staff = true означает доступ к системе. is_superuser = true означает доступ к Django Admin (/admin/).'),
        }),
    )

    add_fieldsets = (
        ('Основная информация', {
            'fields': (
                'username', 'password1', 'password2',
                'first_name', 'last_name', 'email',
                'is_active', 'is_staff',
                'primary_company', 'primary_department', 'profile_job_title',
            ),
            'classes': ('wide',),
        }),
        ('Права доступа', {
            'fields': ('is_superuser', 'groups'),
            'classes': ('wide',),
        }),
    )

    readonly_fields = ('get_timezone', 'get_phone', 'get_address', 'get_specialization', 'get_responsibilities')

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj=obj)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        return tuple(fieldset for fieldset in fieldsets if fieldset[0] != 'Права доступа')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if hasattr(form, 'save_profile'):
            form.save_profile(obj)

    def get_company(self, obj):
        """???????? ???????? ???????? ????????????"""
        try:
            profile = getattr(obj, 'userprofile', None)
            if profile and profile.primary_company:
                return mark_safe(
                    f'<a href="/admin/work_orders/usercompanymembership/?user_id__exact={obj.id}">{profile.primary_company.name}</a>'
                )

            membership = UserCompanyMembership.objects.filter(
                user=obj,
                is_primary=True,
                is_active=True,
                date_to__isnull=True
            ).select_related('company').first()

            if not membership:
                membership = UserCompanyMembership.objects.filter(
                    user=obj,
                    is_active=True,
                    date_to__isnull=True
                ).select_related('company').first()

            if membership:
                return mark_safe(
                    f'<a href="/admin/work_orders/usercompanymembership/?user_id__exact={obj.id}">{membership.company.name}</a>'
                )

            return mark_safe('<span class="badge bg-secondary">??? ????????</span>')
        except Exception:
            return mark_safe('<span class="badge bg-secondary">??????</span>')

    get_company.short_description = 'Компания'

    def get_memberships_info(self, obj):
        """Информация о множественных членствах в компаниях"""
        try:
            from work_orders.models import UserCompanyMembership
            memberships = UserCompanyMembership.objects.filter(
                user=obj,
                is_active=True,
                date_to__isnull=True
            ).select_related('company', 'department').order_by('-is_primary', 'company__name')

            if not memberships.exists():
                return mark_safe('<span class="text-muted">Нет активных членств</span>')

            html = ['<div style="max-height: 200px; overflow-y: auto;">']
            for m in memberships:
                primary_badge = ' <span class="badge bg-primary">Основная</span>' if m.is_primary else ''
                html.append(f'<div>{m.company.name} → {m.department.department_name} ({m.get_role_code_display()}){primary_badge}</div>')
            html.append('</div>')

            return mark_safe(''.join(html))
        except Exception:
            return mark_safe('<span class="text-danger">Ошибка загрузки</span>')
    get_memberships_info.short_description = 'Членства в компаниях'

    def get_timezone(self, obj):
        """Получить timezone из UserProfile"""
        try:
            profile = obj.userprofile
            return profile.timezone or 'Не указан'
        except UserProfile.DoesNotExist:
            return 'Europe/Moscow (по умолчанию)'
    get_timezone.short_description = 'Часовой пояс'

    def get_phone(self, obj):
        """Получить телефон из UserProfile"""
        try:
            profile = obj.userprofile
            return profile.phone or 'Не указан'
        except UserProfile.DoesNotExist:
            return 'Не указан'
    get_phone.short_description = 'Телефон'

    def get_address(self, obj):
        """Получить адрес из UserProfile"""
        try:
            profile = obj.userprofile
            return profile.address or 'Не указан'
        except UserProfile.DoesNotExist:
            return 'Не указан'
    get_address.short_description = 'Адрес'

    def get_specialization(self, obj):
        """Получить специализацию из UserProfile"""
        try:
            profile = obj.userprofile
            return profile.get_specialization_display() if profile.specialization else 'Не указана'
        except UserProfile.DoesNotExist:
            return 'Не указана'
    get_specialization.short_description = 'Специализация'

    def get_job_title(self, obj):
        """Получить должность из UserProfile"""
        try:
            profile = obj.userprofile
            return profile.get_job_title_display() if profile.job_title else 'Не указана'
        except UserProfile.DoesNotExist:
            return 'Не указана'
    get_job_title.short_description = 'Должность'

    def get_responsibilities(self, obj):
        """Получить обязанности из UserProfile"""
        try:
            profile = obj.userprofile
            return profile.responsibilities or 'Не указаны'
        except UserProfile.DoesNotExist:
            return 'Не указаны'
    get_responsibilities.short_description = 'Обязанности'

    def get_dates_info(self, obj):
        """Форматирует даты в одну строку: 'Создан {date_joined}, последний вход {last_login}'"""
        from django.utils import timezone
        parts = []

        # Дата создания
        if obj.date_joined:
            local_joined = timezone.localtime(obj.date_joined)
            joined_str = local_joined.strftime('%d.%m.%Y %H:%M')
            parts.append(f'Создан {joined_str}')
        else:
            parts.append('Создан не указан')

        # Последний вход
        if obj.last_login:
            local_login = timezone.localtime(obj.last_login)
            login_str = local_login.strftime('%d.%m.%Y %H:%M')
            parts.append(f'последний вход {login_str}')
        else:
            parts.append('последний вход: никогда')

        return mark_safe(f'<span class="text-muted">{", ".join(parts)}</span>')
    get_dates_info.short_description = 'Даты'

    def get_role(self, obj):
        """
        Получить роль пользователя из UserCompanyMembership

        ПРИОРИТЕТ:
        1. Primary membership
        2. Любая активная membership
        3. UserProfile.role (fallback)
        """
        try:
            from work_orders.models import UserCompanyMembership

            # Сначала пробуем UserCompanyMembership
            membership = UserCompanyMembership.objects.filter(
                user=obj,
                is_primary=True,
                is_active=True,
                date_to__isnull=True
            ).first()

            if not membership:
                # Если нет primary - берем любую активную
                membership = UserCompanyMembership.objects.filter(
                    user=obj,
                    is_active=True,
                    date_to__isnull=True
                ).first()

            if membership:
                # Формируем badge на основе role_code
                role_labels = {
                    'django_admin': ('Администратор Django', 'danger'),
                    'direktor_uk': ('Директор УК', 'warning'),
                    'chief_engineer': ('Главный инженер', 'primary'),
                    'executor': ('Исполнитель', 'info'),
                    'uk_user': ('Пользователь УК', 'secondary'),
                    'resident': ('Житель', 'secondary'),
                    'contractor': ('Подрядчик', 'secondary'),
                }

                label, color = role_labels.get(membership.role_code, (membership.role_code, 'secondary'))
                return mark_safe(f'<span class="badge bg-{color}">{label}</span>')

            # Fallback на UserProfile.role
            profile = obj.userprofile
            if profile.role == 'django_admin':
                return mark_safe('<span class="badge bg-danger">Администратор Django (старый)</span>')
            elif profile.role == 'direktor_uk':
                return mark_safe('<span class="badge bg-warning">Директор УК (старый)</span>')
            elif profile.role == 'uk_user':
                return mark_safe('<span class="badge bg-info">Пользователь УК (старый)</span>')
            else:
                return mark_safe(f'<span class="badge bg-secondary">{profile.get_role_display()} (старый)</span>')

        except UserProfile.DoesNotExist:
            return mark_safe('<span class="badge bg-secondary">Нет роли</span>')
    get_role.short_description = 'Роль'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Кастомная страница редактирования"""
        extra_context = extra_context or {}
        return super().change_view(request, object_id, form_url, extra_context)

    class Media:
        css = {
            'all': ('/static/css/admin_custom.css',)
        }


# UserProfileAdmin удален - теперь профиль редактируется через UserAdmin с помощью UserProfileInline
# Это устраняет дублирование в админке: User + Profile теперь в одном месте (/admin/auth/user/)

@admin.register(AIPrompt)
class AIPromptAdmin(admin.ModelAdmin):
    """Администрирование AI промптов"""

    list_display = ('prompt_id', 'prompt_type', 'title', 'is_test_badge', 'is_active', 'updated_at')
    list_filter = ('prompt_type', 'is_test', 'is_active', 'created_at')
    search_fields = ('prompt_id', 'title', 'description')
    ordering = ('prompt_type', 'prompt_id')

    fieldsets = (
        (None, {
            'fields': ('prompt_id', 'prompt_type', 'title', 'is_test', 'is_active'),
            'description': 'Основная информация о промпте'
        }),
        ('Описание', {
            'fields': ('description',),
            'description': 'Опишите для чего используется этот промпт и в каких случаях он применяется'
        }),
        ('Содержание промпта', {
            'fields': ('content',),
            'description': 'Текст промпта для AI. Используйте переменные {username}, {address} и др.',
            'classes': ('wide',),
        }),
        ('Служебная информация', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'description': 'Информация о создании и изменении'
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def is_test_badge(self, obj):
        """Показывает метку [Б] или [Т]"""
        from django.utils.safestring import mark_safe
        if obj.is_test:
            return mark_safe('<span style="color: #ff6b6b; font-weight: bold; background: #ffebeb; padding: 2px 6px; border-radius: 3px;">[Т]</span>')
        else:
            return mark_safe('<span style="color: #51cf66; font-weight: bold; background: #e6fcf5; padding: 2px 6px; border-radius: 3px;">[Б]</span>')
    is_test_badge.short_description = 'Тип'

    def has_delete_permission(self, request, obj=None):
        """Запрещает удаление боевых промптов"""
        if obj is not None and not obj.is_test:
            # Боевой промпт - запрещаем удаление
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем создателя"""
        if not change:  # Только при создании
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    class Media:
        css = {
            'all': ('/static/css/admin_custom.css',)
        }

@admin.register(SemanticPattern)
class SemanticPatternAdmin(admin.ModelAdmin):
    """Админка для семантических паттернов"""

    list_display = [
        'pattern_type',
        'keyword',
        'weight',
        'is_active',
        'notes_preview'
    ]

    list_filter = ['pattern_type', 'is_active']
    search_fields = ['keyword', 'notes']
    list_editable = ['is_active', 'weight']
    ordering = ['pattern_type', '-weight', 'keyword']

    fieldsets = (
        ('Основное', {
            'fields': ('pattern_type', 'keyword', 'weight')
        }),
        ('Статус и метаданные', {
            'fields': ('is_active', 'notes')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def notes_preview(self, obj):
        """Предпросмотр заметок"""
        return obj.notes[:50] + '...' if obj.notes and len(obj.notes) > 50 else obj.notes or ''
    notes_preview.short_description = 'Заметки'


@admin.register(ServicesCatalog)
class ServicesCatalogAdmin(admin.ModelAdmin):
    """Админка для услуг из services_catalog

    НОВАЯ СТРУКТУРА (с 2026-03-25):
    - Текстовые поля вместо FK
    - 44 услуги (матрица 11×2×2)
    """

    list_display = [
        'service_id',
        'scenario_name',
        'category_name',
        'type_name',
        'localization_name',
        'is_internal',
        'is_active',
    ]

    list_filter = ['is_active', 'is_internal', 'category_name', 'type_name', 'localization_name', 'route_name']
    search_fields = ['scenario_name', 'category_name', 'type_name', 'description', 'route_name']
    list_editable = ['is_active']
    ordering = ['category_name', 'scenario_name']

    fieldsets = (
        ('Основное', {
            'fields': ('service_id', 'scenario_name', 'is_active', 'is_internal')
        }),
        ('Классификация', {
            'fields': ('category_name', 'type_name', 'localization_name', 'route_name')
        }),
        ('Описание', {
            'fields': ('description',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['service_id', 'created_at', 'updated_at']


@admin.register(ServiceObject)
class ServiceObjectAdmin(admin.ModelAdmin):
    """Просмотр объектов обслуживания с поиском по адресу."""

    list_display = ['service_object_id', 'address_display', 'building_id', 'unit_id', 'is_active']
    list_filter = ['is_active']
    search_fields = ['=service_object_id']
    ordering = ['service_object_id']
    readonly_fields = ['service_object_id', 'address_display', 'building_id', 'unit_id', 'created_at', 'is_active']
    fieldsets = (
        ('Объект обслуживания', {
            'fields': ('service_object_id', 'address_display', 'building_id', 'unit_id', 'is_active', 'created_at')
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def address_display(self, obj):
        return obj.get_address_display()
    address_display.short_description = 'Адрес'

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        if not search_term:
            return queryset, use_distinct

        matched_ids = list(search_service_objects(search_term, limit=50).values_list('service_object_id', flat=True))
        if not matched_ids:
            return queryset.none(), use_distinct

        queryset = self.model.objects.filter(service_object_id__in=matched_ids).order_by('service_object_id')
        return queryset, use_distinct
