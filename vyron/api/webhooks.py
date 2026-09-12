"""Payment provider webhooks — the ONLY trusted path that moves money state.

- raw body is signature-verified inside the provider adapter
- events are inserted idempotently (unique provider+event_id)
- amount is re-checked against the stored payment; mismatches never mark paid
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.config import settings
from vyron.db.base import get_db
from vyron.logging import get_logger
from vyron.payments.base import WebhookRequest
from vyron.security.ratelimit import enforce_rate_limit
from vyron.services import payment_service

log = get_logger("vyron.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/payments/{provider}")
async def payment_webhook(provider: str, request: Request, db: DbSession = Depends(get_db)):
    enforce_rate_limit(request, "webhook", settings.rate_limit_webhook)
    raw_body = await request.body()
    webhook_request = WebhookRequest(
        headers={k.lower(): v for k, v in request.headers.items()},
        body=raw_body,
        query={k: v for k, v in request.query_params.items()},
    )
    client_ip = request.client.host if request.client else None

    result = payment_service.handle_webhook(db, provider, webhook_request, client_ip)
    if result.get("duplicate"):
        log.info("duplicate webhook ignored", provider=provider, event_id=result.get("event_id"))
    return ok(result)
