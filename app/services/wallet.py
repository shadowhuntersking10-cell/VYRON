"""Wallet ledger. Balance is only changed together with a ledger row."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.services.pricing import q


class WalletError(Exception):
    pass


def get_or_create(db: Session, user_id: int) -> models.Wallet:
    w = db.query(models.Wallet).filter_by(user_id=user_id).first()
    if not w:
        w = models.Wallet(user_id=user_id, balance=Decimal("0"))
        db.add(w)
        db.flush()
    return w


def apply(db: Session, wallet: models.Wallet, kind: str, amount, reference: str = "", note: str = "") -> models.WalletTransaction:
    amount = q(amount)
    new_balance = q(wallet.balance) + amount
    if new_balance < 0:
        raise WalletError("insufficient_funds")
    wallet.balance = new_balance
    tx = models.WalletTransaction(
        wallet_id=wallet.id, kind=kind, amount=amount,
        balance_after=new_balance, reference=reference, note=note,
    )
    db.add(tx)
    db.flush()
    return tx


def deposit(db: Session, user_id: int, amount, reference: str = "") -> models.WalletTransaction:
    if q(amount) <= 0:
        raise WalletError("invalid_amount")
    return apply(db, get_or_create(db, user_id), "deposit", amount, reference)


def spend(db: Session, user_id: int, amount, reference: str = "") -> models.WalletTransaction:
    if q(amount) <= 0:
        raise WalletError("invalid_amount")
    return apply(db, get_or_create(db, user_id), "spend", -q(amount), reference)


def credit_refund(db: Session, user_id: int, amount, reference: str = "") -> models.WalletTransaction:
    if q(amount) <= 0:
        raise WalletError("invalid_amount")
    return apply(db, get_or_create(db, user_id), "refund_credit", amount, reference)
