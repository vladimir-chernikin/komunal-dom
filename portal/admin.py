from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import render
from django.http import HttpResponseRedirect
from .models import UserProfile, AIPrompt


# Отключаем стандартную регистрацию User
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Красивый интерфейс редактирования пользователя"""

    list_display = ('username', 'email', 'first_name', 'last_name', 'get_role', 'is_active', 'date_joined')
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
                return format_html('<span class="badge bg-danger">Администратор Django</span>')
            elif profile.role == 'dba':
                return format_html('<span class="badge bg-warning">DBA</span>')
            elif profile.role == 'uk_user':
                return format_html('<span class="badge bg-info">Пользователь УК</span>')
            else:
                return format_html('<span class="badge bg-secondary">Житель</span>')
        except UserProfile.DoesNotExist:
            return format_html('<span class="badge bg-secondary">Без роли</span>')
    get_role.short_description = 'Роль'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Кастомная страница редактирования"""
        extra_context = extra_context or {}
        return super().change_view(request, object_id, form_url, extra_context)

    class Media:
        css = {
            'all': ('/static/css/admin_custom.css',)
        }


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Администрирование профилей пользователей"""

    list_display = ('user', 'role', 'phone', 'get_building_count')
    list_filter = ('role', 'created_at')
    search_fields = ('user__username', 'user__email', 'phone')
    raw_id_fields = ('user',)

    fieldsets = (
        (None, {
            'fields': ('user', 'role'),
            'description': 'Связь с пользователем системы и его роль'
        }),
        ('Контактная информация', {
            'fields': ('phone', 'address'),
            'description': 'Дополнительная контактная информация'
        }),
        ('Служебная информация', {
            'fields': ('created_at',),
            'description': 'Дата создания профиля'
        }),
    )

    readonly_fields = ('created_at',)

    def get_building_count(self, obj):
        """Получить количество связанных зданий"""
        # Здесь можно добавить логику подсчета зданий, если есть связь
        return '-'

    get_building_count.short_description = 'Здания'

    class Media:
        css = {
            'all': ('/static/css/admin_custom.css',)
        }


@admin.register(AIPrompt)
class AIPromptAdmin(admin.ModelAdmin):
    """Администрирование AI промптов"""

    list_display = ('prompt_id', 'prompt_type', 'title', 'is_active', 'updated_at')
    list_filter = ('prompt_type', 'is_active', 'created_at')
    search_fields = ('prompt_id', 'title', 'description')
    ordering = ('prompt_type', 'prompt_id')

    fieldsets = (
        (None, {
            'fields': ('prompt_id', 'prompt_type', 'title', 'is_active'),
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

    def save_model(self, request, obj, form, change):
        """Автоматически устанавливаем создателя"""
        if not change:  # Только при создании
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    class Media:
        css = {
            'all': ('/static/css/admin_custom.css',)
        }