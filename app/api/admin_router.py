"""Admin JSON API. EVERY route requires ADMIN (server-side)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.service import get_admin_service
from app.database import get_db
from app.dependencies import require_admin
from app.models import (
    AuditLog, Coupon, DonationProfile, Game, GameCategory, MarketplaceListing,
    Notification, Order, OrderStatus, Payment, Product, ProductVariant, Promotion,
    Seller, SellerPayout, Setting, Supplier, SupportMessage, SupportTicket, User, UserRole,
)
from app.services import audit_service, settings_service, support_service
from app.services.notification_service import notify_user
from app.services.payout_service import set_status as payout_set_status
from app.services.revenue_service import revenue_summary
from app.utils.helpers import client_ip
from app.utils.money import D
from app.utils.pagination import pagination_params

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _ip(request: Request) -> str:
    return client_ip(request.headers)


# ---------- dashboard ----------
@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    svc = get_admin_service()
    return {"metrics": await svc.dashboard(db), "timeseries": await svc.timeseries(db)}


# ---------- users ----------
@router.get("/users")
async def users(q: str = "", role: str = "", page: int = 1, per_page: int = 20, db: AsyncSession = Depends(get_db)):
    page, per_page = pagination_params(page, per_page)
    stmt = select(User).order_by(User.id.desc())
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")))
    if role:
        try:
            stmt = stmt.where(User.role == UserRole(role))
        except ValueError:
            pass
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [{"id": u.id, "email": u.email, "username": u.username, "role": u.role.value,
                       "is_active": u.is_active, "is_banned": u.is_banned,
                       "created_at": u.created_at.isoformat()} for u in rows]}


class UserPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    is_banned: bool | None = None
    ban_reason: str | None = None


@router.patch("/users/{user_id}")
async def patch_user(user_id: int, data: UserPatch, request: Request,
                     admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user_not_found")
    if data.role:
        try:
            user.role = UserRole(data.role)
        except ValueError:
            raise HTTPException(400, "bad_role") from None
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_banned is not None:
        user.is_banned = data.is_banned
        user.ban_reason = data.ban_reason
    await audit_service.log_action(db, action="user_update", actor_id=admin.id,
                                   entity="user", entity_id=user.id, ip=_ip(request),
                                   meta=data.model_dump())
    await db.commit()
    return {"ok": True}


# ---------- games ----------
class GameIn(BaseModel):
    slug: str
    title: str
    description: str | None = None
    category_id: int | None = None
    logo_url: str | None = None
    banner_url: str | None = None
    fields_schema: list = []
    supplier_id: int | None = None
    is_active: bool = True
    is_featured: bool = False


@router.get("/games")
async def admin_games(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Game).order_by(Game.id))).scalars().all()
    cats = {c.id: c.slug for c in (await db.execute(select(GameCategory))).scalars().all()}
    return [{"id": g.id, "slug": g.slug, "title": g.title, "category": cats.get(g.category_id or 0),
             "is_active": g.is_active, "is_featured": g.is_featured, "logo_url": g.logo_url} for g in rows]


@router.post("/games")
async def create_game(data: GameIn, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Game).where(Game.slug == data.slug))).scalars().first():
        raise HTTPException(400, "slug_taken")
    g = Game(**data.model_dump())
    db.add(g)
    await db.flush()
    await audit_service.log_action(db, action="game_create", actor_id=admin.id, entity="game", entity_id=g.id, ip=_ip(request))
    await db.commit()
    return {"id": g.id}


@router.patch("/games/{game_id}")
async def patch_game(game_id: int, data: GameIn, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    g = await db.get(Game, game_id)
    if not g:
        raise HTTPException(404, "game_not_found")
    for k, v in data.model_dump().items():
        setattr(g, k, v)
    await audit_service.log_action(db, action="game_update", actor_id=admin.id, entity="game", entity_id=g.id, ip=_ip(request))
    await db.commit()
    return {"ok": True}


@router.delete("/games/{game_id}")
async def delete_game(game_id: int, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    g = await db.get(Game, game_id)
    if not g:
        raise HTTPException(404, "game_not_found")
    g.is_active = False
    await audit_service.log_action(db, action="game_disable", actor_id=admin.id, entity="game", entity_id=g.id, ip=_ip(request))
    await db.commit()
    return {"ok": True}


# ---------- products ----------
class ProductIn(BaseModel):
    game_id: int
    name: str
    description: str | None = None
    image_url: str | None = None
    supplier_id: int | None = None
    supplier_product_id: str | None = None
    supplier_cost: float = 0
    selling_price: float = 0
    currency: str = "UZS"
    delivery_type: str = "auto"
    stock: int = -1
    is_active: bool = True
    is_popular: bool = False


@router.get("/products")
async def admin_products(game_id: int | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Product).order_by(Product.id.desc()).limit(200)
    if game_id:
        stmt = select(Product).where(Product.game_id == game_id).order_by(Product.id.desc()).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": p.id, "game_id": p.game_id, "name": p.name, "supplier_cost": str(p.supplier_cost),
             "selling_price": str(p.selling_price), "currency": p.currency, "stock": p.stock,
             "is_active": p.is_active, "is_popular": p.is_popular} for p in rows]


@router.post("/products")
async def create_product(data: ProductIn, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = Product(**{**data.model_dump(), "supplier_cost": D(data.supplier_cost), "selling_price": D(data.selling_price)})
    db.add(p)
    await db.flush()
    await audit_service.log_action(db, action="product_create", actor_id=admin.id, entity="product", entity_id=p.id,
                                   ip=_ip(request), meta={"price": str(data.selling_price)})
    await db.commit()
    return {"id": p.id}


@router.patch("/products/{product_id}")
async def patch_product(product_id: int, data: ProductIn, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = await db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "product_not_found")
    old_price = str(p.selling_price)
    for k, v in data.model_dump().items():
        setattr(p, k, D(v) if k in ("supplier_cost", "selling_price") else v)
    await audit_service.log_action(db, action="price_change", actor_id=admin.id, entity="product", entity_id=p.id,
                                   ip=_ip(request), meta={"old": old_price, "new": str(p.selling_price)})
    await db.commit()
    return {"ok": True}


# ---------- orders ----------
@router.get("/orders")
async def admin_orders(status: str = "", q: str = "", page: int = 1, per_page: int = 20, db: AsyncSession = Depends(get_db)):
    page, per_page = pagination_params(page, per_page)
    stmt = select(Order).order_by(Order.id.desc())
    if status:
        try:
            stmt = stmt.where(Order.status == OrderStatus(status))
        except ValueError:
            pass
    if q:
        stmt = stmt.where(Order.public_id.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [{"id": o.id, "public_id": o.public_id, "status": o.status.value, "total": str(o.total),
                       "currency": o.currency, "user_id": o.user_id, "created_at": o.created_at.isoformat()} for o in rows]}


@router.get("/orders/{order_id}")
async def admin_order_detail(order_id: int, db: AsyncSession = Depends(get_db)):
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order_not_found")
    await db.refresh(order, attribute_names=["items", "payments"])
    return {
        "id": order.id, "public_id": order.public_id, "status": order.status.value,
        "total": str(order.total), "currency": order.currency, "customer_fields": order.customer_fields,
        "timeline": order.timeline,
        "items": [{"title": i.title, "quantity": i.quantity, "unit_price": str(i.unit_price), "kind": i.kind} for i in order.items],
        "payments": [{"id": p.id, "provider": p.provider, "status": p.status.value, "amount": str(p.amount)} for p in order.payments],
    }


class OrderStatusIn(BaseModel):
    status: str
    note: str | None = None


@router.post("/orders/{order_id}/status")
async def admin_order_status(order_id: int, data: OrderStatusIn, request: Request,
                             admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.orders.processor import get_order_processor

    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order_not_found")
    try:
        new_status = OrderStatus(data.status)
    except ValueError:
        raise HTTPException(400, "bad_status") from None
    if new_status == OrderStatus.COMPLETED:
        await get_order_processor().complete_order(db, order)
    elif new_status == OrderStatus.FAILED:
        await get_order_processor().fail_order(db, order, data.note or "manual")
    else:
        order.status = new_status
        order.timeline = (order.timeline or []) + [{"event": f"admin_{new_status.value.lower()}",
                                                    "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                                    "note": data.note}]
        await db.commit()
    await audit_service.log_action(db, action="order_status", actor_id=admin.id, entity="order", entity_id=order.id,
                                   ip=_ip(request), meta={"status": data.status})
    await db.commit()
    return {"ok": True, "status": order.status.value}


# ---------- payments / refunds ----------
@router.get("/payments")
async def admin_payments(page: int = 1, per_page: int = 20, db: AsyncSession = Depends(get_db)):
    page, per_page = pagination_params(page, per_page)
    stmt = select(Payment).order_by(Payment.id.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [{"id": p.id, "order_id": p.order_id, "provider": p.provider, "status": p.status.value,
                       "amount": str(p.amount), "currency": p.currency,
                       "created_at": p.created_at.isoformat()} for p in rows]}


# ---------- suppliers ----------
@router.get("/suppliers")
async def admin_suppliers(db: AsyncSession = Depends(get_db)):
    from app.suppliers.manager import get_supplier_manager

    rows = (await db.execute(select(Supplier))).scalars().all()
    mgr = get_supplier_manager()
    live = {s["code"]: s["configured"] for s in mgr.status_list()}
    return {"db": [{"id": s.id, "code": s.code, "name": s.name, "status": s.status.value,
                    "balance": str(s.balance)} for s in rows],
            "providers": mgr.status_list(), "live": live}


class SupplierIn(BaseModel):
    code: str
    name: str
    api_url: str | None = None
    status: str = "ACTIVE"


@router.post("/suppliers")
async def create_supplier(data: SupplierIn, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.models.catalog import SupplierStatus
    s = Supplier(code=data.code, name=data.name, api_url=data.api_url, status=SupplierStatus(data.status))
    db.add(s)
    await db.flush()
    await audit_service.log_action(db, action="supplier_create", actor_id=admin.id, entity="supplier", entity_id=s.id, ip=_ip(request))
    await db.commit()
    return {"id": s.id}


# ---------- marketplace / sellers / payouts ----------
@router.get("/sellers")
async def admin_sellers(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Seller).order_by(Seller.id.desc()).limit(200))).scalars().all()
    return [{"id": s.id, "user_id": s.user_id, "shop_name": s.shop_name, "is_verified": s.is_verified,
             "is_active": s.is_active, "sales_count": s.sales_count, "rating_avg": str(s.rating_avg)} for s in rows]


@router.post("/sellers/{seller_id}/verify")
async def verify_seller(seller_id: int, verified: bool = True, request: Request = None,  # type: ignore[assignment]
                        admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = await db.get(Seller, seller_id)
    if not s:
        raise HTTPException(404, "seller_not_found")
    s.is_verified = verified
    await audit_service.log_action(db, action="seller_verify", actor_id=admin.id, entity="seller", entity_id=s.id,
                                   ip=_ip(request) if request else None)
    await db.commit()
    return {"ok": True}


@router.get("/listings")
async def admin_listings(status: str = "", db: AsyncSession = Depends(get_db)):
    stmt = select(MarketplaceListing).order_by(MarketplaceListing.id.desc()).limit(200)
    if status:
        stmt = select(MarketplaceListing).where(MarketplaceListing.status == status).order_by(MarketplaceListing.id.desc()).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": l.id, "title": l.title, "price": str(l.price), "status": l.status,
             "seller_id": l.seller_id, "is_promoted": l.is_promoted} for l in rows]


@router.get("/payouts")
async def admin_payouts(status: str = "", db: AsyncSession = Depends(get_db)):
    from app.models import PayoutStatus
    stmt = select(SellerPayout).order_by(SellerPayout.id.desc()).limit(200)
    if status:
        try:
            stmt = select(SellerPayout).where(SellerPayout.status == PayoutStatus(status)).order_by(SellerPayout.id.desc()).limit(200)
        except ValueError:
            pass
    rows = (await db.execute(stmt)).scalars().all()
    out = []
    for p in rows:
        seller = await db.get(Seller, p.seller_id)
        out.append({"id": p.id, "seller_id": p.seller_id, "shop": seller.shop_name if seller else "?",
                    "amount": str(p.amount), "status": p.status.value, "method": p.method})
    return out


class PayoutStatusIn(BaseModel):
    status: str
    note: str | None = None


@router.post("/payouts/{payout_id}/status")
async def admin_payout_status(payout_id: int, data: PayoutStatusIn,
                              admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    from app.models import PayoutStatus
    payout = await db.get(SellerPayout, payout_id)
    if not payout:
        raise HTTPException(404, "payout_not_found")
    try:
        st = PayoutStatus(data.status)
    except ValueError:
        raise HTTPException(400, "bad_status") from None
    seller = await db.get(Seller, payout.seller_id)
    await payout_set_status(db, payout, st, admin_id=admin.id, note=data.note,
                            seller_user_id=seller.user_id if seller else None)
    await db.commit()
    return {"ok": True}


# ---------- donations ----------
@router.get("/donations")
async def admin_donations(db: AsyncSession = Depends(get_db)):
    from app.models import Donation
    rows = (await db.execute(select(Donation).order_by(Donation.id.desc()).limit(200))).scalars().all()
    profiles = {p.id: p.username for p in (await db.execute(select(DonationProfile))).scalars().all()}
    return [{"id": d.id, "profile": profiles.get(d.profile_id), "amount": str(d.amount),
             "fee": str(d.platform_fee), "status": d.status} for d in rows]


# ---------- coupons / promotions ----------
class CouponIn(BaseModel):
    code: str
    kind: str = "percent"
    value: float = 0
    min_order: float = 0
    max_uses: int | None = None
    per_user_limit: int = 1
    is_active: bool = True


@router.get("/coupons")
async def admin_coupons(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Coupon).order_by(Coupon.id.desc()).limit(200))).scalars().all()
    return [{"id": c.id, "code": c.code, "kind": c.kind, "value": str(c.value),
             "used_count": c.used_count, "is_active": c.is_active} for c in rows]


@router.post("/coupons")
async def create_coupon(data: CouponIn, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(Coupon).where(Coupon.code == data.code.upper()))).scalars().first():
        raise HTTPException(400, "code_taken")
    c = Coupon(code=data.code.upper(), kind=data.kind, value=D(data.value), min_order=D(data.min_order),
               max_uses=data.max_uses, per_user_limit=data.per_user_limit, is_active=data.is_active)
    db.add(c)
    await db.flush()
    await audit_service.log_action(db, action="coupon_create", actor_id=admin.id, entity="coupon", entity_id=c.id, ip=_ip(request))
    await db.commit()
    return {"id": c.id}


@router.post("/coupons/{coupon_id}/toggle")
async def toggle_coupon(coupon_id: int, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    c = await db.get(Coupon, coupon_id)
    if not c:
        raise HTTPException(404, "coupon_not_found")
    c.is_active = not c.is_active
    await audit_service.log_action(db, action="coupon_toggle", actor_id=admin.id, entity="coupon", entity_id=c.id, ip=_ip(request))
    await db.commit()
    return {"ok": True, "is_active": c.is_active}


class PromoIn(BaseModel):
    slug: str
    title: str
    description: str | None = None
    banner_url: str | None = None
    is_active: bool = True


@router.get("/promotions")
async def admin_promos(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Promotion).order_by(Promotion.id.desc()).limit(100))).scalars().all()
    return [{"id": p.id, "slug": p.slug, "title": p.title, "is_active": p.is_active} for p in rows]


@router.post("/promotions")
async def create_promo(data: PromoIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    p = Promotion(**data.model_dump())
    db.add(p)
    await db.commit()
    return {"id": p.id}


# ---------- revenue ----------
@router.get("/revenue")
async def admin_revenue(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return await revenue_summary(db, since=since)


# ---------- support ----------
@router.get("/support")
async def admin_support(status: str = "", db: AsyncSession = Depends(get_db)):
    stmt = select(SupportTicket).order_by(SupportTicket.id.desc()).limit(200)
    if status:
        stmt = select(SupportTicket).where(SupportTicket.status == status).order_by(SupportTicket.id.desc()).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": t.id, "subject": t.subject, "category": t.category, "status": t.status,
             "user_id": t.user_id} for t in rows]


class AdminReplyIn(BaseModel):
    body: str


@router.post("/support/{ticket_id}/reply")
async def admin_reply(ticket_id: int, data: AdminReplyIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket_not_found")
    await support_service.reply(db, ticket, sender_id=admin.id, body=data.body, is_admin=True)
    await db.commit()
    return {"ok": True}


@router.post("/support/{ticket_id}/status")
async def admin_ticket_status(ticket_id: int, status: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket_not_found")
    try:
        await support_service.set_status(db, ticket, status)
    except ValueError:
        raise HTTPException(400, "bad_status") from None
    await db.commit()
    return {"ok": True}


# ---------- broadcast notifications ----------
class BroadcastIn(BaseModel):
    title: str
    body: str | None = None
    link: str | None = None


@router.post("/notifications/broadcast")
async def broadcast(data: BroadcastIn, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    ids = (await db.execute(select(User.id).where(User.is_active.is_(True)).limit(5000))).scalars().all()
    for uid in ids:
        await notify_user(db, user_id=uid, kind="promotion", title=data.title, body=data.body,
                          link=data.link, push_telegram=False)
    await audit_service.log_action(db, action="broadcast", actor_id=admin.id, meta={"count": len(ids), "title": data.title})
    await db.commit()
    return {"ok": True, "count": len(ids)}


# ---------- telegram info ----------
@router.get("/telegram")
async def admin_telegram(db: AsyncSession = Depends(get_db)):
    from app.config import settings as _s
    from app.models import TelegramUser
    total = (await db.execute(select(func.count(TelegramUser.id)))).scalar() or 0
    return {"bot_configured": _s.telegram_configured, "webapp_url": _s.TELEGRAM_WEBAPP_URL,
            "admin_ids": sorted(_s.admin_telegram_ids), "linked_users": total,
            "payments": None}


# ---------- fraud (heuristic overview) ----------
@router.get("/fraud")
async def admin_fraud(db: AsyncSession = Depends(get_db)):
    # Heuristics: users with many failed payments / many orders in 1h.
    hour_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    recent_orders = (await db.execute(select(Order.user_id, func.count(Order.id)).where(
        Order.created_at >= hour_ago, Order.user_id.is_not(None)).group_by(Order.user_id)
        .having(func.count(Order.id) > 5))).all()
    return {"suspicious_users_last_hour": [{"user_id": u, "orders": c} for u, c in recent_orders],
            "note": "Heuristic overview. Extend with provider risk signals in production."}


# ---------- audit ----------
@router.get("/audit")
async def admin_audit(page: int = 1, per_page: int = 30, db: AsyncSession = Depends(get_db)):
    page, per_page = pagination_params(page, per_page)
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    return {"total": total, "page": page, "per_page": per_page,
            "items": [{"id": a.id, "actor_id": a.actor_id, "action": a.action, "entity": a.entity,
                       "entity_id": a.entity_id, "ip": a.ip, "meta": a.meta,
                       "created_at": a.created_at.isoformat()} for a in rows]}


# ---------- settings ----------
@router.get("/settings")
async def admin_settings(db: AsyncSession = Depends(get_db)):
    return await settings_service.all_settings(db)


class SettingIn(BaseModel):
    value: str


@router.put("/settings/{key}")
async def admin_set_setting(key: str, data: SettingIn, request: Request,
                            admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await settings_service.set_setting(db, key, data.value)
    await audit_service.log_action(db, action="settings_change", actor_id=admin.id, entity="setting",
                                   entity_id=key, ip=_ip(request), meta={"value": data.value[:100]})
    await db.commit()
    return {"ok": True}
