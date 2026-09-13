"""Wallet API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app import models
from app.config import settings
from app.dependencies import Db, require_user
from app.payments.service import PaymentError, PaymentService
from app.schemas import DepositIn
from app.services import orders as order_svc
from app.services import wallet as wallet_svc
from app.services.pricing import q
from app.utils.security import new_token

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("")
def get_wallet(request: Request, db: Db):
    user = require_user(request, db)
    w = wallet_svc.get_or_create(db, user.id)
    db.commit()
    txs = db.query(models.WalletTransaction).filter_by(wallet_id=w.id).order_by(
        models.WalletTransaction.id.desc()).limit(50).all()
    return {"balance": str(w.balance), "currency": w.currency,
            "transactions": [{"kind": t.kind, "amount": str(t.amount),
                              "balance_after": str(t.balance_after), "ref": t.reference,
                              "created_at": t.created_at.isoformat()} for t in txs]}


@router.post("/deposit")
def deposit(body: DepositIn, request: Request, db: Db):
    user = require_user(request, db)
    amount = q(body.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    order = models.Order(public_id=order_svc.public_id(), user_id=user.id, kind="wallet",
                         status="PENDING_PAYMENT", currency=settings.DEFAULT_CURRENCY,
                         subtotal=amount, total=amount, idempotency_key=new_token(24))
    db.add(order)
    db.flush()
    db.add(models.OrderItem(order_id=order.id, title="Wallet top-up", quantity=1,
                            unit_price=amount, total_price=amount))
    order_svc.push_timeline(order, "CREATED", "wallet top-up")
    db.commit()
    try:
        payment, action = PaymentService(db).create_for_order(
            order, body.provider, return_url=f"{settings.BASE_URL}/profile")
    except PaymentError as e:
        raise HTTPException(status_code=400, detail=e.key)
    return {"order": order.public_id, "payment": {"id": payment.id, "status": payment.status}, "action": action}
