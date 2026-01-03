from django.urls import path
from . import views
from . import admin_views
from . import kladr_views
from django.conf import settings
from django.conf.urls.static import static

app_name = 'portal'

urlpatterns = [
    path('', views.welcome, name='welcome'),
    path('test-logo/', views.test_logo_variants, name='test_logo'),
    path('subscribers/', views.subscriber_page, name='subscriber_page'),
    path('regulatory-chat/', views.regulatory_chat, name='regulatory_chat'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('executor/', views.executor_dashboard, name='executor_dashboard'),
    path('admin-uk/', admin_views.admin_page, name='admin_page'),
    path('dba/', admin_views.dba_page, name='dba_page'),
    path('admin-uk/users/', admin_views.user_management, name='user_management'),
    path('admin-uk/prompts/', admin_views.prompt_management, name='prompt_management'),

    # КЛАДР управление
    path('admin-uk/kladr/', kladr_views.kladr_management, name='kladr_management'),
    path('admin-uk/kladr/objects/', kladr_views.kladr_objects_list, name='kladr_objects'),
    path('admin-uk/kladr/objects/<int:object_id>/', kladr_views.kladr_object_detail, name='kladr_object_detail'),
    path('admin-uk/kladr/buildings/', kladr_views.buildings_list, name='kladr_buildings'),
    path('admin-uk/kladr/buildings/<int:building_id>/', kladr_views.building_detail, name='kladr_building_detail'),
    path('admin-uk/kladr/service-areas/', kladr_views.service_areas_list, name='kladr_service_areas'),
    path('admin-uk/kladr/service-areas/<int:area_id>/', kladr_views.service_area_detail, name='kladr_service_area_detail'),
    path('admin-uk/kladr/import-logs/', kladr_views.import_logs_list, name='kladr_import_logs'),

    # Трассировка диалогов
    path('admin-uk/dialog-trace/', views.dialog_trace_page, name='dialog_trace'),
    path('admin-uk/dialog-trace/<str:filename>/', views.dialog_report_view_page, name='dialog_report_view'),
    path('api/dialog-trace/', views.dialog_trace_api, name='api_dialog_trace'),
    path('api/dialog-sessions/', views.api_dialog_sessions, name='api_dialog_sessions'),
    path('api/dialog-reports/', views.api_dialog_reports, name='api_dialog_reports'),
    path('api/dialog-reports/<str:filename>/', views.api_dialog_report_view, name='api_dialog_report_view'),
    path('api/dialog-full-trace/', views.api_dialog_full_trace, name='api_dialog_full_trace'),  # ✅ ДОБАВЛЕНО

    # API
    path('api/kladr/search/', kladr_views.api_search_kladr, name='api_search_kladr'),
]