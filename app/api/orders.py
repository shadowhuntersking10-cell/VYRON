from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Order, User
from app.schemas import OrderOut

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def my_orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Order).where(Order.user_id == user.id).order_by(Order.id.desc()).limit(50)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{public_id}", response_model=OrderOut)
async def order_detail(public_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    order = (await db.execute(select(Order).where(Order.public_id == public_id))).scalars().first()
    if not order or (order.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(404, "order_not_found")
    return order
