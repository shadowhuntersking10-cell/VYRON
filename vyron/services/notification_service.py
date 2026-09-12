"""Notification service — website + email + Telegram channels.

Events fan out through queues (emails/telegram) so the request path stays
fast. Email goes through a real outbox table; if SMTP is not configured the
outbox row is marked SKIPPED with a reason (visible to admins, never faked).
Telegram messages are sent by the telegram worker ONLY when a verified
TelegramConnection exists.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.db.models import EmailOutbox, Notification, TelegramConnection, User
from vyron.enums import NotificationType, QueueName
from vyron.i18n import t
from vyron.logging import get_logger
from vyron.queue.engine import Queue

log = get_logger("vyron.notifications")

EVENT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "welcome": {"title": "notify.welcome_title", "body": "notify.welcome_body", "email": True},
    "email_verified": {"title": "notify.email_verified_title", "body": "notify.email_verified_body"},
    "payment_success": {"title": "notify.payment_success_title", "body": "notify.payment_success_body", "email": True, "telegram": True},
    "payment_failed": {"title": "notify.payment_failed_title", "body": "notify.payment_failed_body", "telegram": True},
    "order_processing": {"title": "notify.order_processing_title", "body": "notify.order_processing_body", "telegram": True},
    "order_delivering": {"title": "notify.order_delivering_title", "body": "notify.order_delivering_body", "telegram": True},
    "order_completed": {"title": "notify.order_completed_title", "body": "notify.order_completed_body", "email": True, "telegram": True},
    "order_failed": {"title": "notify.order_failed_title", "body": "notify.order_failed_body", "email": True, "telegram": True},
    "order_review": {"title": "notify.order_review_title", "body": "notify.order_review_body", "telegram": True},
    "refund_issued": {"title": "notify.refund_issued_title", "body": "notify.refund_issued_body", "email": True, "telegram": True},
    "donation_received": {"title": "notify.donation_received_title", "body": "notify.donation_received_body", "email": True, "telegram": True},
    "payout_status": {"title": "notify.payout_title", "body": "notify.payout_body", "email": True, "telegram": True},
    "listing_reviewed": {"title": "notify.listing_reviewed_title", "body": "notify.listing_reviewed_body", "telegram": True},
    "seller_order": {"title": "notify.seller_order_title", "body": "notify.seller_order_body", "telegram": True},
    "support_response": {"title": "notify.support_response_title", "body": "notify.support_response_body", "email": True, "telegram": True},
    "password_changed": {"title": "notify.password_changed_title", "body": "notify.password_changed_body", "email": True},
    "telegram_linked": {"title": "notify.telegram_linked_title", "body": "notify.telegram_linked_body"},
}


def notify_event(
    db: DbSession,
    user: User,
    event: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    link: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> Notification:
    """Create a site notification and fan out to email/telegram per template."""
    params = params or {}
    template = EVENT_TEMPLATES.get(event, {})
    lang = user.locale or "uz"
    title = t(template.get("title", "notify.welcome_title"), lang, **params)
    body = t(template.get("body", "notify.welcome_body"), lang, **params)

    notification = Notification(
        user_id=user.id,
        type=event.upper() if event.upper() in NotificationType.__members__ else NotificationType.MARKETING.value,
        title=title[:200],
        body=body,
        data=data or params,
        link=link,
    )
    db.add(notification)

    if template.get("email") and user.email:
        queue_email(
            db,
            to_email=user.email,
            subject=title,
            body_text=body,
            user_id=user.id,
            idempotency_key=f"{event}:{user.id}:{params.get('number') or params.get('id') or ''}",
            commit=False,
        )
    if template.get("telegram"):
        connection = db.query(TelegramConnection).filter(TelegramConnection.user_id == user.id).first()
        if connection is not None:
            Queue(QueueName.TELEGRAM.value).enqueue(
                "send_telegram_message",
                {"telegram_id": connection.telegram_id, "text": f"{title}\n\n{body}", "user_id": user.id},
                dedupe_key=f"{event}:{user.id}:{params.get('number') or params.get('id') or ''}",
            )
    if commit:
        db.commit()
    return notification


def queue_email(
    db: DbSession,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    user_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    commit: bool = True,
) -> EmailOutbox:
    if idempotency_key:
        existing = db.query(EmailOutbox).filter(EmailOutbox.idempotency_key == idempotency_key).first()
        if existing:
            return existing
    outbox = EmailOutbox(
        user_id=user_id,
        to_email=to_email,
        subject=subject[:300],
        body_text=body_text,
        body_html=body_html or _wrap_html(subject, body_text),
        idempotency_key=idempotency_key,
    )
    db.add(outbox)
    if commit:
        db.commit()
        Queue(QueueName.EMAILS.value).enqueue("send_email", {"outbox_id": outbox.id}, dedupe_key=f"email:{outbox.id}")
    else:
        db.flush()
        Queue(QueueName.EMAILS.value).enqueue("send_email", {"outbox_id": outbox.id}, dedupe_key=f"email:{outbox.id}")
    return outbox


def _wrap_html(subject: str, body: str) -> str:
    safe_subject = (subject or "").replace("<", "&lt;")
    safe_body = (body or "").replace("<", "&lt;").replace("\n", "<br>")
    return (
        '<div style="font-family:Inter,Segoe UI,Arial,sans-serif;background:#0b1220;padding:24px">'
        '<div style="max-width:560px;margin:0 auto;background:#111a2e;border-radius:16px;padding:28px;color:#dbe7ff">'
        '<div style="font-size:22px;font-weight:800;color:#7fb3ff;letter-spacing:2px">VYRON</div>'
        f'<h2 style="margin:18px 0 8px;color:#ffffff;font-size:18px">{safe_subject}</h2>'
        f'<p style="line-height:1.6;color:#b8c7e6">{safe_body}</p>'
        '<hr style="border:none;border-top:1px solid #24345a;margin:20px 0">'
        '<p style="color:#6c7ea6;font-size:12px">VYRON — PLAY. BUY. DONATE.</p>'
        "</div></div>"
    )


def mark_notifications_read(db: DbSession, user_id: str, notification_id: Optional[str] = None) -> int:
    from vyron.db.base import utcnow

    query = db.query(Notification).filter(Notification.user_id == user_id, Notification.read_at.is_(None))
    if notification_id:
        query = query.filter(Notification.id == notification_id)
    count = query.update({"read_at": utcnow()}, synchronize_session=False)
    db.commit()
    return count
