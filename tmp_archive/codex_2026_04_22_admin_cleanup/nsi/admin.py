from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Company, EquipmentType, RefCategory


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Админка для справочника компаний"""

    list_display = ['linked_id', 'linked_name', 'phone_display', 'director_display', 'domain', 'is_active_display', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'full_name', 'domain', 'phone']
    ordering = ['name']
    actions = None  # Отключаем bulk actions

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'full_name', 'director', 'is_active')
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
    change_list_template = 'nsi/company_change_list.html'

    def linked_id(self, obj):
        """ID как гиперссылка"""
        url = f'/admin/nsi/company/{obj.id}/change/'
        return mark_safe(f'<a href="{url}">{obj.id}</a>')
    linked_id.short_description = 'ID'
    linked_id.admin_order_field = 'id'

    def linked_name(self, obj):
        """Название как гиперссылка"""
        url = f'/admin/nsi/company/{obj.id}/change/'
        return mark_safe(f'<a href="{url}">{obj.name}</a>')
    linked_name.short_description = 'Наименование'
    linked_name.admin_order_field = 'name'

    def phone_display(self, obj):
        """Телефон (отдельное поле)"""
        return obj.phone if obj.phone else mark_safe('<span style="color: gray;">—</span>')
    phone_display.short_description = 'Телефон'
    phone_display.admin_order_field = 'phone'

    def director_display(self, obj):
        """Директор с ссылкой"""
        if obj.director:
            url = f'/admin/auth/user/{obj.director.id}/change/'
            return mark_safe(f'<a href="{url}">{obj.director.get_full_name() or obj.director.username}</a>')
        return mark_safe('<span style="color: gray;">—</span>')
    director_display.short_description = 'Директор'
    director_display.admin_order_field = 'director'

    def is_active_display(self, obj):
        """Активна с визуальным отображением"""
        if obj.is_active:
            return mark_safe('<span style="color: green;">✓ Да</span>')
        return mark_safe('<span style="color: red;">✗ Нет</span>')
    is_active_display.short_description = 'Активна'
    is_active_display.admin_order_field = 'is_active'
    is_active_display.boolean = False


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

    list_display = ['category_id', 'linked_category_name', 'is_default_display', 'dev_notes_preview']
    list_filter = ['is_default']
    search_fields = ['category_name', 'llm_description']
    ordering = ['category_id']
    actions = ['set_as_default']

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
    )

    readonly_fields = ['category_id']

    def linked_category_name(self, obj):
        """Возвращает название категории как гиперссылку на форму редактирования"""
        url = f'/admin/nsi/refcategory/{obj.category_id}/change/'
        return mark_safe(f'<a href="{url}">{obj.category_name}</a>')
    linked_category_name.short_description = 'Категория'
    linked_category_name.admin_order_field = 'category_name'

    def is_default_display(self, obj):
        """Отображает is_default с эмодзи для наглядности"""
        if obj.is_default:
            return mark_safe('<span style="color: green; font-size: 16px;">⭐ Да</span>')
        return mark_safe('<span style="color: gray;">—</span>')
    is_default_display.short_description = 'По умолчанию'
    is_default_display.admin_order_field = 'is_default'
    is_default_display.boolean = False

    def dev_notes_preview(self, obj):
        """Показывает preview dev_notes (обрезает до 50 символов)"""
        if obj.dev_notes:
            notes = obj.dev_notes
            if len(notes) > 50:
                return f'{notes[:50]}...'
            return notes
        return mark_safe('<span style="color: gray;">—</span>')
    dev_notes_preview.short_description = 'Заметки разработчика'

    def set_as_default(self, request, queryset):
        """Admin action: установить выбранную категорию как default"""
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одну категорию для установки как "по умолчанию"', level='ERROR')
            return

        category = queryset.first()
        from nsi.models import RefCategory
        # Сбрасываем is_default у всех
        RefCategory.objects.all().update(is_default=False)
        # Устанавливаем для выбранной
        category.is_default = True
        category.save()

        self.message_user(request, f'Категория "{category.category_name}" установлена как "по умолчанию"')
    set_as_default.short_description = '⭐ Установить выбранную категорию как "По умолчанию"'

    change_list_template = 'nsi/refcategory_change_list.html'
