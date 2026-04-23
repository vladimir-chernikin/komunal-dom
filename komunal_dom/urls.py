"""
URL configuration for komunal_dom project.

The `urlpatterns` list routes URLs to views. For more information please see:
https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
1. Add an import:  from my_app import views
2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
1. Add an import:  from other_app.views import Home
2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
1. Import the include() function:  from django.urls import include, path
2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import path, include, re_path
from .admin import configure_admin_navigation
from .views import custom_logout, admin_login_redirect

# Стандартный admin site
admin_site = admin.site
configure_admin_navigation(admin_site)


def redirect_legacy_company_route_mapping(request, rest=''):
    target = f'/admin/work_orders/companyserviceroute/{rest}'
    query_string = request.META.get('QUERY_STRING')
    if query_string:
        target = f'{target}?{query_string}'
    return redirect(target, permanent=True)

urlpatterns = [
    path('', include('portal.urls')),  # Главная страница
    path('admin/login/', admin_login_redirect),  # Redirect на /login/ (ДО admin.site.urls!)
    re_path(
        r'^admin/work_orders/companyroutemapping/(?P<rest>.*)$',
        redirect_legacy_company_route_mapping,
    ),
    path('admin/', admin_site.urls),  # Стандартный admin site
    path('logout/', custom_logout, name='logout'),
    path('chat/', include('message_handler.urls')),  # Веб-чат с AI
    path('llm-tester/', include('llm_tester.urls')),  # LLM Tester
    path('db-sql/', include('database_viewer.urls')),  # СУБД SQL интерфейс
    path('work_orders/', include('work_orders.urls')),  # Управление заявками ЖКХ
]

# Обслуживание медиа-файлов в режиме разработки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
