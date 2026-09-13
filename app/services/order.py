from __future__ import annotations
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import Order, OrderItem, Product, Coupon, CouponUsage, User
from app.utils.security import generate_order_number, generate_idempotency_key
from app.utils.helpers import to_decimal, quantize_money
from app.services.pricing import PricingService
import logging

logger = logging.getLogger(__name__)

class OrderService:
    @staticmethod
    async def create_order(
        db: AsyncSession,
        user_id: int,
        items: List[Dict[str, Any]],
        payment_provider: str = "PAYME",
        coupon_code: Optional[str] = None,
        game_data: Optional[Dict[str, Any]] = None,
        currency: str = "UZS"
    ) -> tuple[bool, str, Optional[Order]]:
        from app.config import settings
        
        if not settings.SALES_ENABLED:
            return False, "Sales are temporarily disabled", None

        # Validate items
        if not items:
            return False, "No items in order", None

        subtotal = Decimal("0.00")
        order_items_data = []

        for item in items:
            product_id = item.get("product_id")
            quantity = item.get("quantity", 1)
            
            result = await db.execute(select(Product).where(Product.id == product_id, Product.is_active == True))
            product = result.scalar_one_or_none()
            if not product:
                return False, f"Product {product_id} not found or inactive", None

            unit_price = product.customer_price
            total_price = unit_price * quantity
            subtotal += total_price

            order_items_data.append({
                "product": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "game_data": item.get("game_data") or game_data
            })

        # Coupon handling
        discount_amount = Decimal("0.00")
        coupon = None
        if coupon_code:
            result = await db.execute(select(Coupon).where(Coupon.code == coupon_code, Coupon.is_active == True))
            coupon = result.scalar_one_or_none()
            if not coupon:
                return False, "Invalid coupon code", None
            
            # Validate coupon
            # Check expiration
            from datetime import datetime
            now = datetime.utcnow()
            if coupon.valid_from and now < coupon.valid_from:
                return False, "Coupon not yet valid", None
            if coupon.valid_until and now > coupon.valid_until:
                return False, "Coupon expired", None
            if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
                return False, "Coupon usage limit reached", None
            
            # Check per user limit
            result = await db.execute(
                select(CouponUsage).where(
                    CouponUsage.coupon_id == coupon.id,
                    CouponUsage.user_id == user_id
                )
            )
            usages = result.scalars().all()
            if len(usages) >= coupon.per_user_limit:
                return False, "Coupon per-user limit reached", None

            # Check min order
            if coupon.min_order_amount and subtotal < coupon.min_order_amount:
                return False, f"Minimum order amount for this coupon is {coupon.min_order_amount}", None

            # Calculate discount
            if coupon.discount_type == "percentage":
                discount_amount = subtotal * coupon.discount_value / Decimal("100")
                if coupon.max_discount_amount and discount_amount > coupon.max_discount_amount:
                    discount_amount = coupon.max_discount_amount
            else:  # fixed
                discount_amount = coupon.discount_value

            discount_amount = quantize_money(discount_amount)
            if discount_amount > subtotal:
                discount_amount = subtotal

        service_fee = Decimal("0.00")  # Could be configurable
        total_amount = subtotal - discount_amount + service_fee
        total_amount = quantize_money(total_amount)

        if total_amount <= 0:
            return False, "Invalid order total", None

        # Create order
        order_number = generate_order_number()
        idempotency_key = generate_idempotency_key()

        order = Order(
            order_number=order_number,
            user_id=user_id,
            status="PENDING_PAYMENT",
            currency=currency,
            subtotal=quantize_money(subtotal),
            discount_amount=discount_amount,
            service_fee=service_fee,
            total_amount=total_amount,
            payment_provider=payment_provider,
            coupon_code=coupon_code,
            game_data=game_data,
            idempotency_key=idempotency_key
        )
        db.add(order)
        await db.flush()

        # Create order items
        for item_data in order_items_data:
            product = item_data["product"]
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                total_price=item_data["total_price"],
                supplier_cost=product.supplier_cost,
                meta=item_data["game_data"]
            )
            db.add(order_item)

        # Handle coupon usage
        if coupon:
            coupon.used_count += 1
            usage = CouponUsage(
                coupon_id=coupon.id,
                user_id=user_id,
                order_id=order.id,
                discount_amount=discount_amount
            )
            db.add(usage)

        await db.commit()
        await db.refresh(order)

        logger.info(f"Order created: {order.order_number} for user {user_id}, total {total_amount}")

        # Create notification
        try:
            from app.models.models import Notification
            notif = Notification(
                user_id=user_id,
                type="ORDER_CREATED",
                title="Order Created",
                message=f"Your order {order.order_number} has been created. Please complete payment.",
                data={"order_id": order.id, "order_number": order.order_number}
            )
            db.add(notif)
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to create notification: {e}")

        return True, "Order created", order

    @staticmethod
    async def get_user_orders(db: AsyncSession, user_id: int, page: int = 1, per_page: int = 20):
        from sqlalchemy import func
        offset = (page - 1) * per_page
        
        result = await db.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).offset(offset).limit(per_page)
        )
        orders = result.scalars().all()

        count_result = await db.execute(select(func.count(Order.id)).where(Order.user_id == user_id))
        total = count_result.scalar()

        return orders, total
