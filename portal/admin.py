from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.shortcuts import render
from django.http import HttpResponseRedirect
from .models import UserProfile, AIPrompt, SemanticPattern, ServicesCatalog
from nsi.models import RefCategory


# Отключаем стандартную регистрацию User
admin.site.unregister(User)


class UserProfileInline(admin.TabularInline):
    """Inline для редактирования профиля пользователя на странице User"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль пользователя'
    fields = ('role', 'phone', 'address')
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Красивый интерфейс редактирования пользователя"""

    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_active', 'date_joined')
    inlines = [UserProfileInline]
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {
            'fields': ('username', 'password'),
            'classes': ('wide',),
            'description': 'Основные данные для входа в систему'
        }),
        ('Личная информация', {
            'fields': ('first_name', 'last_name', 'email'),
            'classes': ('wide',),
        }),
        ('Права доступа', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('wide',),
        }),
        ('Важные даты', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('wide',),
        }),
    )

    def get_role(self, obj):
        """Получить роль пользователя"""
        try:
            profile = obj.userprofile
            if profile.role == 'django_admin':
                return mark_safe('<span class="badge bg-danger">Администратор Django</span>')
            elif profile.role == 'direktor_uk':
                return mark_safe('<span class="badge bg-warning">Директор УК</span>')
            elif profile.role == 'uk_user':
                return mark_safe('<span class="badge bg-info">Пользователь УК</span>')
            else:
                return mark_safe('<span class="badge bg-secondary">Житель</span>')
        except UserProfile.DoesNotExist:
            return mark_safe('<span class="badge bg-secondary">Без роли</span>')
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

