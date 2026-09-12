"""Model → JSON serializers shared by the API and web layers.

Money values serialize as strings (never floats). Supplier cost and other
internal fields are NEVER included in customer-facing payloads.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from vyron.db.models import (
    Coupon,
    Donation,
    DonationPage,
    Game,
    ListingPromotion,
    Order,
    OrderItem,
    Payment,
    PayoutRequest,
    Product,
    ProductVariant,
    SellerBalance,
    SellerListing,
    SellerOrder,
    SellerProfile,
    Supplier,
    SupportMessage,
    SupportTicket,
    User,
)
from vyron.enums import UserRole
from vyron.money import to_money
from vyron.security.crypto import decrypt_str

STAFF_ROLE_VALUES = {r.value for r in UserRole if r != UserRole.USER and r != UserRole.SELLER}


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _dec(value) -> Optional[str]:
    return str(to_money(value)) if value is not None else None


# --- identity -------------------------------------------------------------------------------
def user_public(user: User) -> Dict[str, Any]:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "avatar_url": user.avatar_url,
        "locale": user.locale,
        "theme": user.theme,
        "role": user.role,
        "status": user.status,
        "email_verified": user.email_verified,
        "is_staff": user.role in STAFF_ROLE_VALUES,
        "created_at": _iso(user.created_at),
    }


def user_admin(user: User) -> Dict[str, Any]:
    data = user_public(user)
    data.update({"last_login_at": _iso(user.last_login_at), "fraud_risk_score": user.fraud_risk_score})
    return data


# --- catalog ----------------------------------------------------------------------------------
def game_public(game: Game) -> Dict[str, Any]:
    return {
        "id": game.id,
        "name": game.name,
        "slug": game.slug,
        "description": game.description,
        "logo_url": game.logo_url,
        "banner_url": game.banner_url,
        "accent_color": game.accent_color,
        "status": game.status,
        "is_featured": game.is_featured,
        "sort_order": game.sort_order,
    }


def variant_public(variant: ProductVariant) -> Dict[str, Any]:
    return {
        "id": variant.id,
        "name": variant.name,
        "selling_price": _dec(variant.selling_price),
        "currency": variant.currency,
        "stock": variant.stock,
        "in_stock": variant.stock < 0 or variant.stock > 0,  # stock < 0 = unlimited (digital)
        "active": variant.active,
        "sort_order": variant.sort_order,
    }


def variant_admin(variant: ProductVariant) -> Dict[str, Any]:
    data = variant_public(variant)
    cost = to_money(variant.cost_price) if variant.cost_price is not None else Decimal("0.00")
    price = to_money(variant.selling_price)
    margin = price - cost
    data.update(
        {
            "cost_price": _dec(variant.cost_price),
            "margin": str(to_money(margin)),
            "margin_pct": str(to_money(margin / price * 100)) if price > 0 else "0.00",
            "external_product_id": variant.external_product_id,
            "product_id": variant.product_id,
            "metadata": variant.metadata or {},
            "created_at": _iso(variant.created_at),
        }
    )
    return data


def product_public(product: Product) -> Dict[str, Any]:
    variants = sorted((v for v in product.variants if v.active), key=lambda v: (v.sort_order, v.selling_price))
    cheapest = variants[0] if variants else None
    return {
        "id": product.id,
        "slug": product.slug,
        "name": product.name,
        "type": product.type,
        "description": product.description,
        "image_url": product.image_url,
        "game": {"id": product.game.id, "name": product.game.name, "slug": product.game.slug} if product.game else None,
        "is_featured": product.is_featured,
        "required_fields": product.effective_required_fields,
        "from_price": _dec(cheapest.selling_price) if cheapest else None,
        "currency": cheapest.currency if cheapest else "USD",
        "variants": [variant_public(v) for v in variants],
    }


def product_admin(product: Product) -> Dict[str, Any]:
    return {
        "id": product.id,
        "slug": product.slug,
        "name": product.name,
        "type": product.type,
        "description": product.description,
        "image_url": product.image_url,
        "game_id": product.game_id,
        "game_name": product.game.name if product.game else None,
        "is_featured": product.is_featured,
        "active": product.active,
        "sort_order": product.sort_order,
        "required_fields": product.required_fields or [],
        "variants": [variant_admin(v) for v in product.variants],
        "created_at": _iso(product.created_at),
    }


# --- cart & checkout ------------------------------------------------------------------------------
def cart_payload(calc: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize the dict returned by cart_service.calculate()."""
    items = []
    for line in calc["lines"]:
        variant: ProductVariant = line["variant"]
        product: Optional[Product] = line["product"]
        items.append(
            {
                "item_id": line["item_id"],
                "variant_id": variant.id,
                "quantity": line["quantity"],
                "product_name": product.name if product else "",
                "product_slug": product.slug if product else "",
                "product_image": product.image_url if product else None,
                "game_name": line["game"].name if line.get("game") else None,
                "variant_name": variant.name,
                "unit_price": str(line["unit_price"]),
                "line_total": str(line["line_total"]),
                "currency": variant.currency,
                "required_field_values": line["required_field_values"],
                "required_fields": [
                    {"key": f.get("key"), "label": f.get("label"), "type": f.get("type", "text"), "required": f.get("required", True)}
                    for f in (line.get("required_fields") or [])
                ],
                "in_stock": variant.stock < 0 or variant.stock >= line["quantity"],
            }
        )
    totals = {
        "subtotal": str(calc["subtotal"]),
        "discount": str(calc["discount"]),
        "service_fee": str(calc["service_fee"]),
        "total": str(calc["total"]),
        "currency": calc.get("currency", "USD"),
        "coupon_code": calc["cart"].coupon_code,
        "coupon_error": calc.get("coupon_error"),
    }
    return {"items": items, "totals": totals}


# --- orders -------------------------------------------------------------------------------------
def order_item_public(item: OrderItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "product_name": item.product_name,
        "variant_name": item.variant_name,
        "game_name": item.game_name,
        "unit_price": _dec(item.unit_price),
        "quantity": item.quantity,
        "total": _dec(item.total),
        "currency": item.currency,
        "delivery_state": item.delivery_state,
        "required_field_values": item.required_field_values or {},
    }


def _order_timeline(order: Order) -> List[Dict[str, Any]]:
    return [
        {"from": h.from_status, "to": h.to_status, "reason": h.reason, "at": _iso(h.created_at)}
        for h in sorted(order.status_history, key=lambda x: x.created_at)
    ]


def order_public(order: Order) -> Dict[str, Any]:
    return {
        "id": order.id,
        "number": order.number,
        "status": order.status,
        "subtotal": _dec(order.subtotal),
        "discount": _dec(order.discount),
        "service_fee": _dec(order.service_fee),
        "total": _dec(order.total),
        "currency": order.currency,
        "payment_provider": order.payment_provider,
        "customer_note": order.customer_note,
        "failure_reason": order.failure_reason,
        "created_at": _iso(order.created_at),
        "paid_at": _iso(order.paid_at),
        "completed_at": _iso(order.completed_at),
        "cancelled_at": _iso(order.cancelled_at),
        "items": [order_item_public(i) for i in order.items],
        "timeline": _order_timeline(order),
    }


def order_admin(order: Order) -> Dict[str, Any]:
    data = order_public(order)
    data.update(
        {
            "user": {"id": order.user.id, "username": order.user.username, "email": order.user.email, "name": order.user.name} if order.user else None,
            "risk_score": order.risk_score,
            "risk_level": order.risk_level,
            "supplier_cost_total": _dec(order.supplier_cost_total),
            "ip_address": order.ip_address,
            "coupon_id": order.coupon_id,
            "payment": payment_public(order.payments[-1]) if order.payments else None,
        }
    )
    return data


def payment_public(payment: Payment) -> Dict[str, Any]:
    return {
        "id": payment.id,
        "provider": payment.provider,
        "provider_payment_id": payment.provider_payment_id,
        "purpose": payment.purpose,
        "amount": _dec(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "checkout_url": payment.checkout_url,
        "failure_reason": payment.failure_reason,
        "processing_fee": _dec(payment.processing_fee),
        "refunded_amount": _dec(payment.refunded_amount),
        "paid_at": _iso(payment.paid_at),
        "expires_at": _iso(payment.expires_at),
        "created_at": _iso(payment.created_at),
    }


# --- donations -----------------------------------------------------------------------------------
def donation_public(donation: Donation) -> Dict[str, Any]:
    return {
        "id": donation.id,
        "amount": _dec(donation.amount),
        "gross_amount": _dec(donation.gross_amount),
        "currency": donation.currency,
        "donor_name": None if donation.anonymous else donation.donor_name,
        "anonymous": donation.anonymous,
        "message": donation.message,
        "status": donation.status,
        "completed_at": _iso(donation.completed_at),
        "created_at": _iso(donation.created_at),
    }


def donation_page_public(data: Dict[str, Any]) -> Dict[str, Any]:
    page: DonationPage = data["page"]
    user: User = data["user"]
    return {
        "username": user.username,
        "display_name": user.name,
        "avatar_url": user.avatar_url or page.avatar_url,
        "title": page.title,
        "description": page.description,
        "goal_amount": _dec(page.goal_amount),
        "raised": str(data["raised"]),
        "count": data["count"],
        "currency": page.currency,
        "recent": [donation_public(d) for d in data["recent"]],
        "top_supporters": data["top_supporters"],
    }


# --- marketplace ----------------------------------------------------------------------------------
def listing_public(listing: SellerListing) -> Dict[str, Any]:
    return {
        "id": listing.id,
        "title": listing.title,
        "description": listing.description,
        "price": _dec(listing.price),
        "currency": listing.currency,
        "delivery_type": listing.delivery_type,
        "images": listing.images or [],
        "is_promoted": listing.is_promoted,
        "status": listing.status,
        "views": listing.views,
        "rejection_reason": listing.rejection_reason,
        "game": {"id": listing.game.id, "name": listing.game.name} if listing.game else None,
        "seller": seller_public(listing.seller) if listing.seller else None,
        "created_at": _iso(listing.created_at),
    }


def seller_public(profile: SellerProfile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "username": profile.user.username if profile.user else "",
        "avatar_url": profile.avatar_url,
        "rating": str(profile.rating),
        "rating_count": profile.rating_count,
        "completed_orders": profile.completed_orders,
        "verification_status": profile.verification_status,
        "member_since": _iso(profile.created_at),
        "description": profile.description,
    }


def seller_order_public(order: SellerOrder, *, viewer: str = "buyer", seller_profile: Optional[SellerProfile] = None) -> Dict[str, Any]:
    data = {
        "id": order.id,
        "number": order.number,
        "status": order.status,
        "price": _dec(order.price),
        "currency": order.currency,
        "title": order.listing.title if order.listing else "",
        "delivery_type": order.listing.delivery_type if order.listing else None,
        "images": (order.listing.images or []) if order.listing else [],
        "created_at": _iso(order.created_at),
        "delivered_at": _iso(order.delivered_at),
        "completed_at": _iso(order.completed_at),
    }
    if viewer == "buyer":
        data["seller"] = seller_public(seller_profile) if seller_profile else None
        data["delivery_note"] = order.delivery_note
    else:
        data["buyer"] = {"name": order.buyer.name, "username": order.buyer.username} if order.buyer else None
        data["seller_earning"] = _dec(order.seller_earning)
        data["platform_fee"] = _dec(order.platform_fee)
        data["commission_pct"] = _dec(order.commission_pct)
        data["delivery_note"] = order.delivery_note
    return data


def balance_public(balance: SellerBalance) -> Dict[str, Any]:
    return {
        "pending": _dec(balance.pending),
        "available": _dec(balance.available),
        "reserved": _dec(balance.reserved),
        "lifetime_earnings": _dec(balance.lifetime_earnings),
        "lifetime_paid": _dec(balance.lifetime_paid),
    }


def payout_public(payout: PayoutRequest, *, decrypt_details: bool = False, seller: Optional[SellerProfile] = None) -> Dict[str, Any]:
    data = {
        "id": payout.id,
        "amount": _dec(payout.amount),
        "currency": payout.currency,
        "method": payout.method,
        "status": payout.status,
        "review_note": payout.review_note,
        "reference": payout.reference,
        "created_at": _iso(payout.created_at),
        "processed_at": _iso(payout.processed_at),
    }
    if decrypt_details and payout.details_enc:
        data["details"] = decrypt_str(payout.details_enc)
    if seller is not None:
        data["seller"] = {"display_name": seller.display_name, "username": seller.user.username if seller.user else ""}
    return data


# --- marketing / admin ------------------------------------------------------------------------------
def coupon_admin(coupon: Coupon) -> Dict[str, Any]:
    return {
        "id": coupon.id,
        "code": coupon.code,
        "type": coupon.type,
        "value": str(coupon.value),
        "currency": coupon.currency,
        "max_discount": _dec(coupon.max_discount),
        "max_uses": coupon.max_uses,
        "used_count": coupon.used_count,
        "per_user_limit": coupon.per_user_limit,
        "min_order_amount": _dec(coupon.min_order_amount),
        "game_ids": coupon.game_ids or [],
        "product_ids": coupon.product_ids or [],
        "starts_at": _iso(coupon.starts_at),
        "expires_at": _iso(coupon.expires_at),
        "active": coupon.active,
    }


def promotion_admin(promo: ListingPromotion, listing: Optional[SellerListing] = None, seller: Optional[SellerProfile] = None) -> Dict[str, Any]:
    return {
        "id": promo.id,
        "listing_id": promo.listing_id,
        "listing_title": listing.title if listing else "",
        "seller_name": seller.display_name if seller else "",
        "kind": promo.kind,
        "price": _dec(promo.price),
        "currency": promo.currency,
        "status": promo.status,
        "days": promo.days,
        "starts_at": _iso(promo.starts_at),
        "ends_at": _iso(promo.ends_at),
        "created_at": _iso(promo.created_at),
    }


def supplier_admin(supplier: Supplier) -> Dict[str, Any]:
    """NEVER includes config/encrypted_config (credentials stay server-side)."""
    return {
        "id": supplier.id,
        "name": supplier.name,
        "slug": supplier.slug,
        "provider_kind": supplier.provider_kind,
        "status": supplier.status,
        "priority": supplier.priority,
        "active": supplier.active,
        "balance": _dec(supplier.balance),
        "balance_currency": supplier.balance_currency,
        "balance_checked_at": _iso(supplier.balance_checked_at),
        "last_sync_at": _iso(supplier.last_sync_at),
        "last_error": supplier.last_error,
        "success_rate_30d": str(supplier.success_rate_30d) if supplier.success_rate_30d is not None else None,
        "created_at": _iso(supplier.created_at),
    }


# --- support & notifications -------------------------------------------------------------------------
def ticket_message_public(message: SupportMessage) -> Dict[str, Any]:
    return {
        "id": message.id,
        "author_name": message.author_name,
        "author_role": message.author_role,
        "body": message.body,
        "is_internal": message.is_internal,
        "created_at": _iso(message.created_at),
    }


def ticket_public(ticket: SupportTicket, viewer_role: str) -> Dict[str, Any]:
    is_staff = viewer_role in STAFF_ROLE_VALUES
    messages = [ticket_message_public(m) for m in ticket.messages if (is_staff or not m.is_internal)]
    return {
        "id": ticket.id,
        "number": ticket.number,
        "subject": ticket.subject,
        "status": ticket.status,
        "priority": ticket.priority,
        "order_id": ticket.order_id,
        "created_at": _iso(ticket.created_at),
        "last_message_at": _iso(ticket.last_message_at),
        "messages": messages,
        "user": {"name": ticket.user.name, "username": ticket.user.username} if ticket.user else None,
    }


def notification_public(n) -> Dict[str, Any]:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "data": n.data or {},
        "read": n.read_at is not None,
        "created_at": _iso(n.created_at),
    }
