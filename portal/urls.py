from django.urls import path
from . import views
from . import admin_views
from . import kladr_views

app_name = 'portal'

urlpatterns = [
    path('', views.main_page, name='main_page'),
    path('subscribers/', views.subscriber_page, name='subscriber_page'),
    path('dashboard/', views.dashboard, name='dashboard'),
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

    # API
    path('api/kladr/search/', kladr_views.api_search_kladr, name='api_search_kladr'),
]