from __future__ import annotations
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import User, Order, OrderItem
from app.services.order import OrderService
from app.schemas.order import CheckoutRequest
from typing import List

router = APIRouter(prefix="/api/orders", tags=["orders"])

@router.post("/checkout")
async def checkout(
    payload: CheckoutRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Convert items
    items = [{"product_id": i.product_id, "quantity": i.quantity, "game_data": i.game_data} for i in payload.items]
    
    success, message, order = await OrderService.create_order(
        db,
        user_id=current_user.id,
        items=items,
        payment_provider=payload.payment_provider,
        coupon_code=payload.coupon_code,
        game_data=payload.game_data
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {
        "success": True,
        "message": message,
        "order": {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": float(order.total_amount),
            "currency": order.currency,
            "payment_provider": order.payment_provider
        }
    }

@router.get("/")
async def list_orders(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    orders, total = await OrderService.get_user_orders(db, current_user.id, page, per_page)
    
    return {
        "items": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total_amount": float(o.total_amount),
                "currency": o.currency,
                "payment_provider": o.payment_provider,
                "created_at": o.created_at.isoformat(),
                "updated_at": o.updated_at.isoformat()
            } for o in orders
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page -1)//per_page if total else 1
    }

@router.get("/{order_id}")
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Order).where(Order.id == order_id, Order.user_id == current_user.id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Get items
    result = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    items = result.scalars().all()

    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "subtotal": float(order.subtotal),
        "discount_amount": float(order.discount_amount),
        "service_fee": float(order.service_fee),
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "payment_provider": order.payment_provider,
        "coupon_code": order.coupon_code,
        "game_data": order.game_data,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "product_name": i.product_name,
                "quantity": i.quantity,
                "unit_price": float(i.unit_price),
                "total_price": float(i.total_price)
            } for i in items
        ]
    }
