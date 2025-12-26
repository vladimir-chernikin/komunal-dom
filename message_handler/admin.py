from django.contrib import admin
from .models import MessageLog, CommunicativeScript


@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    """Админка для логов сообщений"""

    list_display = [
        'created_at',
        'channel',
        'direction',
        'user_id',
        'text_preview',
        'session_id'
    ]

    list_filter = ['channel', 'direction', 'created_at']
    search_fields = ['text', 'user_id', 'session_id', 'message_id']
    readonly_fields = ['created_at']

    date_hierarchy = 'created_at'

    def text_preview(self, obj):
        """Предпросмотр текста (обрезанный)"""
        return obj.text[:100] + '...' if len(obj.text) > 100 else obj.text
    text_preview.short_description = 'Текст'

    def has_add_permission(self, request):
        """Запрет добавления через админку"""
        return False

    def has_change_permission(self, request, obj=None):
        """Запрет изменения через админку"""
        return False


@admin.register(CommunicativeScript)
class CommunicativeScriptAdmin(admin.ModelAdmin):
    """Админка для коммуникативных скриптов"""

    list_display = [
        'script_name',
        'script_type',
        'channel',
        'text_preview',
        'priority',
        'is_active',
        'updated_at'
    ]

    list_filter = ['script_type', 'channel', 'is_active', 'category']
    search_fields = ['script_name', 'text', 'notes']
    list_editable = ['is_active', 'priority']
    ordering = ['script_type', '-priority', 'script_name']

    fieldsets = (
        ('Основное', {
            'fields': ('script_name', 'script_type', 'channel', 'text')
        }),
        ('Условия использования', {
            'fields': ('conditions', 'priority', 'min_dialog_turn', 'max_dialog_turn', 'max_uses_per_day')
        }),
        ('Статус и метаданные', {
            'fields': ('is_active', 'category', 'notes')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

    def text_preview(self, obj):
        """Предпросмотр текста скрипта"""
        return obj.text[:80] + '...' if len(obj.text) > 80 else obj.text
    text_preview.short_description = 'Текст скрипта'
