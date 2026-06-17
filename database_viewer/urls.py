"""
URL configuration для database_viewer приложения
"""
from django.urls import path
from . import views

app_name = 'database_viewer'

urlpatterns = [
    # Главная страница - список таблиц
    path('', views.table_list, name='table_list'),

    # AJAX endpoints
    path('structure/', views.table_structure, name='table_structure'),
    path('data/', views.table_data, name='table_data'),

    # ER диаграмма
    path('relations/', views.table_relations, name='table_relations'),
]
