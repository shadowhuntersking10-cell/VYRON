"""User wallet: balance + transactions (server-side math, DECIMAL)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Wallet, WalletTransaction
from app.utils.money import D, money_add, money_sub


async def get_or_create_wallet(db: AsyncSession, user_id: int) -> Wallet:
    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user_id))).scalars().first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=D(0))
        db.add(wallet)
        await db.flush()
    return wallet


async def credit(db: AsyncSession, wallet: Wallet, amount, *, kind: str, reference: str | None = None) -> WalletTransaction:
    wallet.balance = money_add(wallet.balance, amount)
    tx = WalletTransaction(
        wallet_id=wallet.id, kind=kind, amount=D(amount),
        balance_after=wallet.balance, reference=reference,
    )
    db.add(tx)
    await db.flush()
    return tx


async def debit(db: AsyncSession, wallet: Wallet, amount, *, kind: str, reference: str | None = None) -> WalletTransaction:
    if D(wallet.balance) < D(amount):
        raise ValueError("insufficient_funds")
    wallet.balance = money_sub(wallet.balance, amount)
    tx = WalletTransaction(
        wallet_id=wallet.id, kind=kind, amount=D(-D(amount)),
        balance_after=wallet.balance, reference=reference,
    )
    db.add(tx)
    await db.flush()
    return tx
