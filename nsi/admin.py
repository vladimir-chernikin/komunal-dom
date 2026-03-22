from django.contrib import admin
from .models import Company, EquipmentType, RefCategory


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


@admin.register(RefCategory)
class RefCategoryAdmin(admin.ModelAdmin):
    """Админка для справочника категорий услуг ЖКХ"""

    list_display = ['category_id', 'category_name', 'is_default', 'created_at']
    list_filter = ['is_default', 'created_at']
    search_fields = ['category_name', 'llm_description']
    list_editable = ['is_default']
    ordering = ['category_id']

    fieldsets = (
        ('Основное', {
            'fields': ('category_id', 'category_name', 'is_default')
        }),
        ('Описание для AI', {
            'fields': ('llm_description',),
            'description': 'Текстовое описание для использования в AI-системах классификации'
        }),
        ('Служебная информация', {
            'fields': ('dev_notes',),
            'classes': ('collapse',),
            'description': 'Заметки разработчиков (не влияет на бизнес-логику)'
        }),
        ('Системная информация', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['category_id', 'created_at']
