from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator


@method_decorator(never_cache, name='__call__')
def admin_login_redirect(request):
    """
    Redirect /admin/login/ → /login/ с сохранением next параметра

    ИСПОЛЬЗУЕТСЯ для унификации точки входа - все пользователи логинятся через /login/

    БЕЗ staff_member_required: иначе цикл редиректа
    """
    next_url = request.GET.get('next', '')
    if next_url and next_url.startswith('/admin/'):
        return redirect(f'/login/?next={next_url}')
    return redirect('/login/')


class CustomAdminSite(admin.AdminSite):
    """
    Кастомный AdminSite с redirect на единый login

    ПЕРЕОПРЕДЕЛЯЕТ:
    - login view → redirect на /login/
    """
    site_header = 'Komunal Dom Administration'
    site_title = 'Komunal Dom Admin'
    index_title = 'Добро пожаловать в панель управления'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('login/', admin_login_redirect, name='login'),
        ]
        # Убираем стандартный login из URL (он будет заменен)
        return custom_urls + [url for url in urls if not hasattr(url, 'name') or url.name != 'login']


# Создаем кастомный admin site
custom_admin_site = CustomAdminSite(name='admin')


ADMIN_NAV_TECHNICAL_MODELS = {
    ('auth', 'Group'),
    ('kladr', 'DataImportLog'),
    ('portal', 'LLMTestResult'),
    ('portal', 'PromptPreset'),
    ('portal', 'PromptTemplate'),
    ('work_orders', 'SLAInstance'),
    ('work_orders', 'WorkOrderAttachment'),
    ('work_orders', 'WorkOrderEventLog'),
}

ADMIN_NAV_DEVELOPER_MODELS = {
    ('message_handler', 'APIErrorLog'),
    ('message_handler', 'MessageLog'),
    ('portal', 'ServiceObject'),
}

ADMIN_NAV_TECHNICAL_ORDER = [
    ('work_orders', 'SLAInstance'),
    ('work_orders', 'WorkOrderEventLog'),
    ('work_orders', 'WorkOrderAttachment'),
    ('auth', 'Group'),
    ('kladr', 'DataImportLog'),
    ('portal', 'PromptTemplate'),
    ('portal', 'PromptPreset'),
    ('portal', 'LLMTestResult'),
]

ADMIN_NAV_DEVELOPER_ORDER = [
    ('portal', 'ServiceObject'),
    ('message_handler', 'APIErrorLog'),
    ('message_handler', 'MessageLog'),
]


def _is_django_admin_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    try:
        return user.company_memberships.filter(
            role_code='django_admin',
            is_active=True,
            date_to__isnull=True,
        ).exists()
    except Exception:
        return False


def _model_key(model_dict):
    model = model_dict.get('model')
    if model is not None:
        return model._meta.app_label, model.__name__
    return model_dict.get('app_label'), model_dict.get('object_name')


def _ordered_models(models_by_key, order):
    ordered = []
    for key in order:
        model_dict = models_by_key.pop(key, None)
        if model_dict is not None:
            ordered.append(model_dict)
    ordered.extend(models_by_key.values())
    return ordered


def _llm_tester_dashboard_link():
    return {
        'name': 'LLM Tester - Тестирование промптов',
        'object_name': 'LLMTesterDashboard',
        'app_label': 'developer_tools',
        'perms': {'view': True, 'add': False, 'change': False, 'delete': False},
        'admin_url': '/llm-tester/',
        'add_url': None,
        'view_only': True,
    }


def configure_admin_navigation(site):
    if getattr(site, '_komunal_navigation_configured', False):
        return

    original_get_app_list = site.get_app_list

    def get_app_list(request, app_label=None):
        app_list = original_get_app_list(request, app_label)
        if app_label is not None:
            return app_list

        is_django_admin = _is_django_admin_user(request.user)
        technical = {}
        developer = {}
        visible_apps = []

        for app in app_list:
            visible_models = []
            for model_dict in app.get('models', []):
                key = _model_key(model_dict)
                if key in ADMIN_NAV_TECHNICAL_MODELS:
                    if is_django_admin:
                        technical[key] = model_dict
                    continue
                if key in ADMIN_NAV_DEVELOPER_MODELS:
                    if is_django_admin:
                        developer[key] = model_dict
                    continue
                visible_models.append(model_dict)

            if visible_models:
                app_copy = dict(app)
                app_copy['models'] = visible_models
                visible_apps.append(app_copy)

        if not is_django_admin:
            return visible_apps

        result = []
        developer_models = [_llm_tester_dashboard_link()]
        developer_models.extend(_ordered_models(developer, ADMIN_NAV_DEVELOPER_ORDER))
        if developer_models:
            result.append({
                'name': 'Разработчик',
                'app_label': 'developer_tools',
                'app_url': '',
                'has_module_perms': True,
                'models': developer_models,
            })

        result.extend(visible_apps)

        if technical:
            result.append({
                'name': 'Технические',
                'app_label': 'technical_tools',
                'app_url': '',
                'has_module_perms': True,
                'models': _ordered_models(technical, ADMIN_NAV_TECHNICAL_ORDER),
            })

        return result

    site.get_app_list = get_app_list
    site._komunal_navigation_configured = True
