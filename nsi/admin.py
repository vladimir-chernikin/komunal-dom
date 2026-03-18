from django.contrib import admin
from .models import Company, EquipmentType


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Админка для справочника компаний"""

    list_display = ['id', 'name', 'domain', 'phone', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'full_name', 'domain', 'phone']
    list_editable = ['is_active']
    ordering = ['name']

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'full_name', 'is_active')
        }),
        ('Контактная информация', {
            'fields': ('domain', 'phone')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']


@admin.register(EquipmentType)
class EquipmentTypeAdmin(admin.ModelAdmin):
    """Админка для справочника видов оборудования"""

    list_display = ['id', 'name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description_for_llm']
    list_editable = ['is_active']
    ordering = ['name']

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'is_active')
        }),
        ('Описание для AI', {
            'fields': ('description_for_llm',),
            'description': 'Подробное описание оборудования для использования в AI-системе (LLM)'
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']
