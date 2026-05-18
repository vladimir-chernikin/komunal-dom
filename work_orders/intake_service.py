"""Compatibility wrapper for the legacy import path.

New code must use work_orders.chat_order_service.ChatOrderService.
"""

from work_orders.chat_order_service import ChatOrderService


ChatIntakeService = ChatOrderService

__all__ = ["ChatOrderService", "ChatIntakeService"]
