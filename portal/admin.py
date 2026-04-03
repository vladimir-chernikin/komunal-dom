from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.shortcuts import render
from django.http import HttpResponseRedirect
from .models import UserProfile, AIPrompt, SemanticPattern, ServicesCatalog
from nsi.models import RefCategory


class UserCompanyMembershipInline(admin.TabularInline):
    """Inline для привязки пользователя к компании с динамической фильтрацией подразделений"""
    from work_orders.models import UserCompanyMembership

    model = UserCompanyMembership
    extra = 0
    verbose_name_plural = 'Основная и дополнительные привязки к компаниям'
    verbose_name = 'Привязка к компании'
    fields = ('company', 'department', 'role_code', 'is_primary', 'is_active', 'date_from', 'date_to')
    autocomplete_fields = ['company', 'department']

    def get_queryset(self, request):
        """Показываем все membership, включая неактивные"""
        qs = super().get_queryset(request)
        return qs.select_related('company', 'department')

    def get_formset(self, request, obj=None, **kwargs):
        """Делаем поле department необязательным (для Директора и др. ролей)"""
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form
        form.department.required = False
        return formset

    class Media:
        js = ('admin/js/company_department_filter.js',)


# Отключаем стандартную регистрацию User
admin.site.unregister(User)


class UserProfileInline(admin.TabularInline):
    """Inline для редактирования личных данных пользователя (без роли, роль в UserCompanyMembership)"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Личные данные (телефон, адрес, специализация)'
    verbose_name = 'Личные данные'
    fields = ('phone', 'address', 'specialization', 'job_title', 'responsibilities')  # Убрали role - она в UserCompanyMembership
    extra = 0


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
    inlines = [UserCompanyMembershipInline, UserProfileInline]  # UserCompanyMembershipInline ПЕРЕД UserProfileInline
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('username', 'password', 'first_name', 'last_name', 'email', 'get_company_link', 'get_timezone', 'get_phone'),
            'classes': ('wide',),
            'description': mark_safe('Основные данные для входа в систему. '
                                   'Текущая привязка к компании показана выше в секции <strong>Основная и дополнительные привязки к компаниям</strong>. '
                                   'Для добавления/изменения привязки используйте эту секцию.')
        }),
        ('Права доступа', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('wide',),
            'description': mark_safe('<strong>ВНИМАНИЕ:</strong> is_staff = true означает доступ к системе. is_superuser = true означает доступ к Django Admin (/admin/).'),
        }),
        ('Важные даты', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('wide',),
        }),
    )

    readonly_fields = ('get_company_link', 'get_timezone', 'get_phone')

    def get_company(self, obj):
        """Получить основную компанию пользователя"""
        try:
            from work_orders.models import UserCompanyMembership
            membership = UserCompanyMembership.objects.filter(
                user=obj,
                is_primary=True,
                is_active=True,
                date_to__isnull=True
            ).select_related('company').first()

            if membership:
                return mark_safe(f'<a href="/admin/work_orders/usercompanymembership/?user_id__exact={obj.id}">{membership.company.name}</a>')
            else:
                # Если нет primary - берем любую активную
                membership = UserCompanyMembership.objects.filter(
                    user=obj,
                    is_active=True,
                    date_to__isnull=True
                ).select_related('company').first()

                if membership:
                    return mark_safe(f'<a href="/admin/work_orders/usercompanymembership/?user_id__exact={obj.id}">{membership.company.name}</a>')

                return mark_safe('<span class="badge bg-secondary">Нет компании</span>')
        except Exception:
            return mark_safe('<span class="badge bg-secondary">Ошибка</span>')
    get_company.short_description = 'Компания'

    def get_company_link(self, obj):
        """Получить ссылку на компанию для readonly поля"""
        company = self.get_company(obj)
        return company
    get_company_link.short_description = 'Компания'

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

