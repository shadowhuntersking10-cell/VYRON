"""Transactional email (stdlib smtplib, sent in a worker thread).

Honest by design: when SMTP is not configured `send_email` returns
(False, "email_not_configured") instead of pretending the mail went out.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

log = logging.getLogger("vyron.email")


def _send_sync(to: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if settings.SMTP_USE_TLS:
        smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        smtp.starttls()
    else:
        smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    try:
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
        smtp.send_message(msg)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass


async def send_email(to: str, subject: str, text: str) -> tuple[bool, str | None]:
    if not settings.smtp_configured:
        return False, "email_not_configured"
    try:
        await asyncio.to_thread(_send_sync, to, subject, text)
        return True, None
    except Exception as exc:  # noqa: BLE001
        log.warning("smtp send failed: %s", exc)
        return False, "email_send_failed"
