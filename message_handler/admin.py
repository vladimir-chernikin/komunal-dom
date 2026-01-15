from django.contrib import admin
from .models import MessageLog, CommunicativeScript


@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    """Админка для логов сообщений"""

    list_display = [
        'timestamp',
        'channel',
        'direction',
        'user_id',
        'text_preview',
        'session_id'
    ]

    list_filter = ['channel', 'direction', 'message_type', 'timestamp']
    search_fields = ['message_content', 'user_id', 'session_id', 'message_id']
    readonly_fields = ['timestamp']

    date_hierarchy = 'timestamp'

    def text_preview(self, obj):
        """Предпросмотр текста (обрезанный)"""
        content = obj.message_content if hasattr(obj, 'message_content') else ''
        if content:
            return content[:100] + '...' if len(content) > 100 else content
        return '-'
    text_preview.short_description = 'Текст'
    text_preview.allow_tags = True

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
        if obj.text:
            return obj.text[:80] + '...' if len(obj.text) > 80 else obj.text
        return '-'
    text_preview.short_description = 'Текст скрипта'
    text_preview.allow_tags = True
