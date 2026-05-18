from django.apps import AppConfig


class WorkOrdersConfig(AppConfig):
    name = 'work_orders'

    def ready(self):
        import work_orders.signals  # noqa: F401
