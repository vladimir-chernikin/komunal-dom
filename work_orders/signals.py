import logging
import threading

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from work_orders.models import WorkOrder

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkOrder)
def notify_max_about_new_work_order(sender, instance: WorkOrder, created: bool, **kwargs):
    if not created or instance.is_test:
        return

    work_order_id = instance.id

    def run_notification():
        try:
            from max_notification_service import notify_new_work_order_by_id

            notify_new_work_order_by_id(work_order_id)
        except Exception as exc:
            logger.error("MAX new work order notification failed: %s", exc, exc_info=True)

    def start_thread():
        thread = threading.Thread(
            target=run_notification,
            name=f"max-work-order-notify-{work_order_id}",
            daemon=True,
        )
        thread.start()

    transaction.on_commit(start_thread)
