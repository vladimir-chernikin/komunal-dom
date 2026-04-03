"""
URL конфигурация для подсистемы управления заявками ЖКХ
"""
from django.urls import path
from . import views

app_name = 'work_orders'

urlpatterns = [
    # Экран исполнителя
    path('executor/', views.ExecutorDashboardView.as_view(), name='executor_dashboard'),

    # Мои заявки (исполнитель)
    path('executor/my-requests/', views.ExecutorMyRequestsView.as_view(), name='executor_my_requests'),

    # Пул подразделения (исполнитель)
    path('executor/pool/', views.ExecutorPoolView.as_view(), name='executor_pool'),

    # Экран подрядчика
    path('contractor/', views.ContractorDashboardView.as_view(), name='contractor_dashboard'),

    # Карточка заявки (сотрудник)
    path('request/<int:work_order_id>/', views.WorkOrderDetailView.as_view(), name='work_order_detail'),

    # Ручное создание заявки
    path('create/', views.WorkOrderCreateView.as_view(), name='work_order_create'),

    # Управленческий список
    path('management/', views.ManagementListView.as_view(), name='management_list'),

    # Экран жителя
    path('resident/', views.ResidentDashboardView.as_view(), name='resident_dashboard'),

    # API для действий
    path('api/<int:work_order_id>/take/', views.api_take_work_order, name='api_take_work_order'),
    path('api/<int:work_order_id>/start/', views.api_start_work_order, name='api_start_work_order'),
    path('api/<int:work_order_id>/complete/', views.api_complete_work_order, name='api_complete_work_order'),
    path('api/<int:work_order_id>/close/', views.api_close_work_order, name='api_close_work_order'),
]
