from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, WalletTransaction
from app.payments.base import ProviderNotConfigured
from app.payments.manager import get_payment_manager
from app.services import wallet_service

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


class TopupIn(BaseModel):
    amount: float
    provider: str = "payme"


@router.post("/topup")
async def topup(data: TopupIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    manager = get_payment_manager()
    try:
        payment = await manager.init_wallet_topup(
            db, user_id=user.id, amount=data.amount,
            currency=settings.DEFAULT_CURRENCY, provider_name=data.provider,
        )
        await db.commit()
    except ProviderNotConfigured:
        return {"payment": None, "error": "payment_provider_not_configured",
                "providers": manager.status_list()}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"payment": {"id": payment.id, "provider": payment.provider,
                        "checkout_url": payment.checkout_url, "status": payment.status.value}}


@router.get("")
async def wallet(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    w = await wallet_service.get_or_create_wallet(db, user.id)
    await db.commit()
    txs = (await db.execute(select(WalletTransaction).where(WalletTransaction.wallet_id == w.id)
                            .order_by(WalletTransaction.id.desc()).limit(30))).scalars().all()
    return {"balance": str(w.balance), "currency": w.currency,
            "transactions": [{"kind": t.kind, "amount": str(t.amount), "balance_after": str(t.balance_after),
                              "reference": t.reference, "created_at": t.created_at.isoformat()} for t in txs]}
