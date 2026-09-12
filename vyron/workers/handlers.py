"""Queue task handlers. Every handler opens its own DB session, commits on success,
and raises RetryJob/DropJob to control redelivery. Nothing is faked: if a channel
(SMTP / Telegram) is not configured the job is recorded as SKIPPED with a reason."""

from __future__ import annotations

import smtplib
import ssl as ssl_module
from email.message import EmailMessage
from typing import Any, Dict, Optional

import httpx
from sqlalchemy import select

from vyron.config import settings
from vyron.db.base import get_session_factory
from vyron.enums import EmailStatus
from vyron.logging import get_logger
from vyron.queue.engine import DropJob, JobContext, RetryJob

log = get_logger("vyron.workers")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _session():
    return get_session_factory()()


# --------------------------------------------------------------------------
# supplier-orders: deliver_order_item
# --------------------------------------------------------------------------
def handle_deliver_order_item(payload: Dict[str, Any], ctx: JobContext) -> None:
    from vyron.services import delivery_service

    order_id = payload.get("order_id")
    item_id = payload.get("order_item_id")
    if not order_id or not item_id:
        raise DropJob("deliver_order_item: missing order_id/order_item_id")

    db = _session()
    try:
        delivery_service.deliver_order_item(db, order_id, item_id)
        db.commit()
    except DropJob:
        db.rollback()
        raise
    except RetryJob:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        log.warning("deliver_order_item failed, will retry", error=str(exc), item=item_id)
        raise RetryJob(str(exc)) from exc
    finally:
        db.close()


# --------------------------------------------------------------------------
# supplier-status: reconcile_supplier_order
# --------------------------------------------------------------------------
def handle_reconcile_supplier_order(payload: Dict[str, Any], ctx: JobContext) -> None:
    from vyron.services import delivery_service

    supplier_order_id = payload.get("supplier_order_id")
    if not supplier_order_id:
        raise DropJob("reconcile_supplier_order: missing supplier_order_id")

    db = _session()
    try:
        delivery_service.reconcile_supplier_order(db, supplier_order_id)
        db.commit()
    except DropJob:
        db.rollback()
        raise
    except RetryJob:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        log.warning("reconcile_supplier_order failed, will retry", error=str(exc), supplier_order=supplier_order_id)
        raise RetryJob(str(exc)) from exc
    finally:
        db.close()


# --------------------------------------------------------------------------
# emails: send_email
# --------------------------------------------------------------------------
def handle_send_email(payload: Dict[str, Any], ctx: JobContext) -> None:
    from vyron.db.base import utcnow
    from vyron.db.models import EmailOutbox

    outbox_id = payload.get("outbox_id")
    if not outbox_id:
        raise DropJob("send_email: missing outbox_id")

    db = _session()
    try:
        outbox = db.get(EmailOutbox, outbox_id)
        if outbox is None:
            raise DropJob(f"send_email: outbox {outbox_id} not found")
        if outbox.status == EmailStatus.SENT.value:
            return  # already delivered — idempotent
        if outbox.status == EmailStatus.SKIPPED.value:
            return

        if not settings.smtp_configured:
            outbox.status = EmailStatus.SKIPPED.value
            outbox.last_error = "SMTP_NOT_CONFIGURED — set SMTP_HOST/SMTP_USER/SMTP_PASSWORD"
            db.commit()
            log.warning("email skipped: SMTP not configured", to=outbox.to_email, subject=outbox.subject)
            return

        _smtp_send(outbox)
        outbox.status = EmailStatus.SENT.value
        outbox.attempts += 1
        outbox.last_error = None
        outbox.sent_at = utcnow()
        db.commit()
        log.info("email sent", to=outbox.to_email, subject=outbox.subject)
    except (DropJob, RetryJob):
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        try:
            outbox = db.get(EmailOutbox, outbox_id)
            if outbox is not None:
                outbox.attempts += 1
                outbox.last_error = str(exc)[:500]
                if outbox.attempts >= 4:
                    outbox.status = EmailStatus.FAILED.value
                db.commit()
        except Exception:
            db.rollback()
        if ctx.attempts >= 4:
            log.error("email permanently failed", to_email_id=outbox_id, error=str(exc))
            return
        raise RetryJob(str(exc)) from exc
    finally:
        db.close()


def _smtp_send(outbox) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = outbox.to_email
    msg["Subject"] = outbox.subject
    msg.set_content(outbox.body_text or "")
    if outbox.body_html:
        msg.add_alternative(outbox.body_html, subtype="html")

    context = ssl_module.create_default_context()
    if settings.smtp_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls(context=context)
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


# --------------------------------------------------------------------------
# telegram: send_telegram_message
# --------------------------------------------------------------------------
def handle_send_telegram_message(payload: Dict[str, Any], ctx: JobContext) -> None:
    telegram_id = payload.get("telegram_id")
    text = payload.get("text") or ""
    if not telegram_id or not text:
        raise DropJob("send_telegram_message: missing telegram_id/text")
    if not settings.telegram_configured:
        log.warning("telegram message skipped: TELEGRAM_BOT_TOKEN not configured", telegram_id=telegram_id)
        return  # nothing to retry against — configuration issue, not transient

    result = telegram_api_call("sendMessage", {
        "chat_id": telegram_id,
        "text": text[:4096],
        "disable_web_page_preview": "true",
    })
    if result is None:
        raise RetryJob("telegram api unreachable")
    if not result.get("ok"):
        desc = str(result.get("description", ""))
        code = int(result.get("error_code", 0))
        if code in (403, 400) and ("blocked" in desc.lower() or "not found" in desc.lower() or "deactivated" in desc.lower()):
            # user blocked the bot / deleted account — stop trying, flag the connection
            log.info("telegram user unreachable, disabling connection", telegram_id=telegram_id, description=desc)
            _disable_connection(telegram_id)
            return
        raise RetryJob(f"telegram api error {code}: {desc}")


def telegram_api_call(method: str, data: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    """Synchronous Bot API call. Returns parsed JSON or None on network failure."""
    if not settings.telegram_configured:
        return None
    url = TELEGRAM_API.format(token=settings.telegram_bot_token, method=method)
    try:
        resp = httpx.post(url, data=data, timeout=timeout)
        return resp.json()
    except Exception as exc:
        log.warning("telegram api network error", method=method, error=str(exc))
        return None


def _disable_connection(telegram_id: int) -> None:
    from vyron.db.models import TelegramConnection

    db = _session()
    try:
        conn = db.scalar(
            select(TelegramConnection).where(TelegramConnection.telegram_id == telegram_id)
        )
        if conn is not None:
            db.delete(conn)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


HANDLERS_BY_QUEUE: Dict[str, Dict[str, Any]] = {
    "supplier-orders": {"deliver_order_item": handle_deliver_order_item},
    "supplier-status": {"reconcile_supplier_order": handle_reconcile_supplier_order},
    "emails": {"send_email": handle_send_email},
    "telegram": {"send_telegram_message": handle_send_telegram_message},
}
