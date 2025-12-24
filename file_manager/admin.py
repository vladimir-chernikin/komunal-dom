from django.contrib import admin
from .models import UserFile


@admin.register(UserFile)
class UserFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'user', 'file_size', 'uploaded_at')
    list_filter = ('user', 'uploaded_at')
    search_fields = ('filename', 'description')
    readonly_fields = ('uploaded_at', 'file_size')
    ordering = ('-uploaded_at',)

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'file', 'filename', 'description')
        }),
        ('Служебная информация', {
            'fields': ('file_size', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )
