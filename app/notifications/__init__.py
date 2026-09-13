"""Notifications domain re-exports (service lives in app.services)."""
from app.services.notification_service import notify_order_event, notify_user, register_telegram_sender

__all__ = ["notify_order_event", "notify_user", "register_telegram_sender"]
