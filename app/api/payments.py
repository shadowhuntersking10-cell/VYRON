from __future__ import annotations
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import User, Order, Payment, PaymentTransaction, RevenueLedger
from app.payments.providers import get_provider, get_all_providers_status
from app.config import settings
from app.utils.security import generate_idempotency_key
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.get("/providers")
async def list_providers():
    status = get_all_providers_status()
    return {
        "providers": [
            {"name": name, "configured": configured, "enabled": settings.PAYMENTS_ENABLED}
            for name, configured in status.items()
        ],
        "payments_enabled": settings.PAYMENTS_ENABLED
    }

@router.post("/create/{order_id}")
async def create_payment(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not settings.PAYMENTS_ENABLED:
        raise HTTPException(status_code=400, detail="Payments are disabled")

    result = await db.execute(select(Order).where(Order.id == order_id, Order.user_id == current_user.id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail=f"Order status is {order.status}, cannot pay")

    provider_name = order.payment_provider or "PAYME"
    provider = get_provider(provider_name)
    if not provider:
        raise HTTPException(status_code=400, detail=f"Unknown provider {provider_name}")

    if not provider.is_configured() and provider_name != "WALLET":
        raise HTTPException(status_code=400, detail=f"PAYMENT_PROVIDER_NOT_CONFIGURED: {provider_name}")

    # Check if payment already exists
    result = await db.execute(select(Payment).where(Payment.order_id == order.id))
    existing = result.scalar_one_or_none()
    if existing and existing.status == "PAID":
        raise HTTPException(status_code=400, detail="Order already paid")

    # Create payment record if not exists
    if not existing:
        payment = Payment(
            order_id=order.id,
            user_id=current_user.id,
            provider=provider_name,
            amount=order.total_amount,
            currency=order.currency,
            status="CREATED",
            idempotency_key=generate_idempotency_key(),
            provider_fee=Decimal("0.00"),
            net_amount=order.total_amount
        )
        db.add(payment)
        await db.flush()
    else:
        payment = existing

    # Call provider
    result_data = await provider.create_payment(
        order_id=order.id,
        amount=order.total_amount,
        currency=order.currency,
        user_id=current_user.id,
        order_number=order.order_number
    )

    if not result_data.get("success"):
        payment.status = "FAILED"
        payment.raw_response = result_data
        await db.commit()
        raise HTTPException(status_code=400, detail=result_data.get("message") or result_data.get("error") or "Payment creation failed")

    payment.provider_payment_id = result_data.get("provider_payment_id")
    payment.raw_request = {"order_id": order.id, "amount": float(order.total_amount)}
    payment.raw_response = result_data
    payment.status = "PENDING"

    # Create transaction
    tx = PaymentTransaction(
        payment_id=payment.id,
        transaction_type="PAYMENT_CREATE",
        amount=payment.amount,
        status="PENDING",
        provider_response=result_data,
        idempotency_key=generate_idempotency_key()
    )
    db.add(tx)
    await db.commit()

    return {
        "success": True,
        "payment": {
            "id": payment.id,
            "provider": payment.provider,
            "amount": float(payment.amount),
            "status": payment.status,
            "provider_payment_id": payment.provider_payment_id
        },
        "provider_data": result_data
    }

@router.post("/webhook/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    body = await request.json() if request.headers.get("content-type", "").find("json") != -1 else {}
    # Try to get raw body for signature verification
    raw_body = await request.body()

    prov = get_provider(provider.upper())
    if not prov:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Verify webhook
    signature = request.headers.get("X-Signature") or request.headers.get("Authorization") or request.headers.get("X-Click-Signature")
    is_valid, msg = await prov.verify_webhook(body, signature)
    if not is_valid:
        logger.warning(f"Webhook verification failed for {provider}: {msg}")
        # Still allow for manual review? But for security, reject
        # For now, log and continue in dev
        if not settings.is_development:
            raise HTTPException(status_code=400, detail=f"Webhook verification failed: {msg}")

    # Process payment confirmation
    # This is simplified - real implementation would parse provider-specific payload
    provider_payment_id = body.get("provider_payment_id") or body.get("transaction_id") or body.get("payment_id")
    order_id = body.get("order_id") or body.get("merchant_trans_id")

    if provider_payment_id:
        result = await db.execute(select(Payment).where(Payment.provider_payment_id == provider_payment_id))
        payment = result.scalar_one_or_none()
        if payment:
            # Idempotency check
            if payment.status == "PAID":
                return {"success": True, "message": "Already paid"}

            payment.status = "PAID"
            from datetime import datetime
            payment.paid_at = datetime.utcnow()

            # Update order
            result = await db.execute(select(Order).where(Order.id == payment.order_id))
            order = result.scalar_one_or_none()
            if order:
                order.status = "PAID"
                
                # Create revenue ledger entry
                ledger = RevenueLedger(
                    transaction_type="SALE",
                    reference_type="ORDER",
                    reference_id=order.id,
                    gross_amount=order.total_amount,
                    supplier_cost=Decimal("0.00"),  # Will be filled when supplier order created
                    payment_fee=payment.provider_fee,
                    platform_fee=order.service_fee,
                    net_revenue=order.total_amount - payment.provider_fee,
                    currency=order.currency,
                    description=f"Payment confirmed for order {order.order_number}"
                )
                db.add(ledger)

            # Transaction
            tx = PaymentTransaction(
                payment_id=payment.id,
                transaction_type="PAYMENT_CONFIRMED",
                amount=payment.amount,
                status="PAID",
                provider_response=body,
                idempotency_key=generate_idempotency_key()
            )
            db.add(tx)
            await db.commit()

            logger.info(f"Payment confirmed via webhook: {provider} - {provider_payment_id}")

            return {"success": True, "message": "Payment confirmed"}

    return {"success": True, "message": "Webhook received, no matching payment found - manual review may be needed"}

@router.post("/confirm-wallet/{order_id}")
async def confirm_wallet_payment(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Wallet payment - deduct from wallet
    from sqlalchemy import select
    from app.models.models import Wallet, WalletTransaction

    result = await db.execute(select(Order).where(Order.id == order_id, Order.user_id == current_user.id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail="Order not in pending state")

    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet or wallet.balance < order.total_amount:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")

    # Deduct
    balance_before = wallet.balance
    wallet.balance -= order.total_amount
    balance_after = wallet.balance

    tx = WalletTransaction(
        wallet_id=wallet.id,
        user_id=current_user.id,
        amount=-order.total_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        transaction_type="PURCHASE",
        reference_type="ORDER",
        reference_id=order.id,
        description=f"Payment for order {order.order_number}",
        idempotency_key=generate_idempotency_key()
    )
    db.add(tx)

    order.status = "PAID"
    
    # Payment record
    result = await db.execute(select(Payment).where(Payment.order_id == order.id))
    payment = result.scalar_one_or_none()
    if not payment:
        payment = Payment(
            order_id=order.id,
            user_id=current_user.id,
            provider="WALLET",
            amount=order.total_amount,
            currency=order.currency,
            status="PAID",
            idempotency_key=generate_idempotency_key(),
            provider_fee=Decimal("0.00"),
            net_amount=order.total_amount
        )
        db.add(payment)
    else:
        payment.status = "PAID"
        from datetime import datetime
        payment.paid_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "message": "Wallet payment confirmed", "order_number": order.order_number}
