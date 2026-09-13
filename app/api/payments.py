"""Provider statuses + verified webhooks."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.dependencies import Db
from app.payments.service import PaymentError, PaymentService

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/providers")
def providers(db: Db):
    return {"providers": PaymentService(db).statuses()}


@router.post("/webhooks/{provider}")
async def webhook(provider: str, request: Request, db: Db):
    try:
        raw = await request.body()
        try:
            data = await request.json()
        except Exception:
            data = dict(await request.form())
        if isinstance(data, dict):
            data["_raw"] = raw.decode("utf-8", "ignore")
        result = PaymentService(db).handle_webhook(provider, data, dict(request.headers))
    except PaymentError as e:
        raise HTTPException(status_code=400, detail=e.key)
    return result
