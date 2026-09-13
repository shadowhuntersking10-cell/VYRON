from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, WalletTransaction
from app.services import wallet_service

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("")
async def wallet(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    w = await wallet_service.get_or_create_wallet(db, user.id)
    await db.commit()
    txs = (await db.execute(select(WalletTransaction).where(WalletTransaction.wallet_id == w.id)
                            .order_by(WalletTransaction.id.desc()).limit(30))).scalars().all()
    return {"balance": str(w.balance), "currency": w.currency,
            "transactions": [{"kind": t.kind, "amount": str(t.amount), "balance_after": str(t.balance_after),
                              "reference": t.reference, "created_at": t.created_at.isoformat()} for t in txs]}
