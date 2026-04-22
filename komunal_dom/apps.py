from django.apps import AppConfig
from django.contrib.admin import admin
from .admin import custom_admin_site


class KomunalDomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'komunal_dom'

    def ready(self):
        """
        Регистрируем все модели из стандартного admin.site в custom_admin_site

        ВЫЗЫВАЕТСЯ при старте Django
        """
        # Копируем все регистрации из admin.site в custom_admin_site
        for model, model_admin in admin.site._registry.items():
            if model not in custom_admin_site._registry:
                custom_admin_site.register(model, model_admin.__class__)
