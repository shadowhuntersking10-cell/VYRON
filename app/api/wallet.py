from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import User, Wallet, WalletTransaction
from decimal import Decimal
from app.utils.security import generate_idempotency_key

router = APIRouter(prefix="/api/wallet", tags=["wallet"])

@router.get("/")
async def get_wallet(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        wallet = Wallet(user_id=current_user.id, balance=Decimal("0.00"), currency="UZS")
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

    # Recent transactions
    tx_result = await db.execute(
        select(WalletTransaction).where(WalletTransaction.wallet_id == wallet.id).order_by(WalletTransaction.created_at.desc()).limit(20)
    )
    transactions = tx_result.scalars().all()

    return {
        "balance": float(wallet.balance),
        "currency": wallet.currency,
        "transactions": [
            {
                "id": t.id,
                "amount": float(t.amount),
                "balance_before": float(t.balance_before),
                "balance_after": float(t.balance_after),
                "type": t.transaction_type,
                "description": t.description,
                "created_at": t.created_at.isoformat()
            } for t in transactions
        ]
    }

@router.post("/deposit")
async def deposit_wallet(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    amount = payload.get("amount")
    if not amount or float(amount) <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    amount_dec = Decimal(str(amount))

    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        wallet = Wallet(user_id=current_user.id, balance=Decimal("0.00"), currency="UZS")
        db.add(wallet)
        await db.flush()

    # In real system, this would require payment confirmation
    # For now, we create a transaction that needs payment
    # But to allow testing, if amount is small and in dev, we allow direct credit with manual review flag?

    # For production safety, we return payment required
    # Actually for wallet top-up, we need to create payment first

    return {
        "success": True,
        "message": "Deposit requires payment. Use payment provider to top up wallet.",
        "amount": float(amount_dec),
        "payment_providers": ["PAYME", "CLICK", "STRIPE"]
    }

@router.post("/credit-manual")
async def credit_manual(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only for development / admin testing - should be removed in production or protected
    from app.config import settings
    if not settings.is_development:
        raise HTTPException(status_code=403, detail="Not allowed in production")

    amount = payload.get("amount")
    if not amount:
        raise HTTPException(status_code=400, detail="Amount required")

    amount_dec = Decimal(str(amount))

    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        wallet = Wallet(user_id=current_user.id, balance=Decimal("0.00"), currency="UZS")
        db.add(wallet)
        await db.flush()

    before = wallet.balance
    wallet.balance += amount_dec
    after = wallet.balance

    tx = WalletTransaction(
        wallet_id=wallet.id,
        user_id=current_user.id,
        amount=amount_dec,
        balance_before=before,
        balance_after=after,
        transaction_type="DEPOSIT",
        description="Manual credit (dev only)",
        idempotency_key=generate_idempotency_key()
    )
    db.add(tx)
    await db.commit()

    return {"success": True, "balance": float(wallet.balance)}
