"""Admin API: every action authorized server-side + audit logged."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import models
from app.config import settings
from app.dependencies import Db, require_admin
from app.services import ledger, notify
from app.services import orders as order_svc
from app.services import settings_service as set_svc
from app.services import wallet as wallet_svc
from app.services.pricing import enforce_price, q, quote_for_product

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(request: Request, db: Db, days: int = 30):
    require_admin(request, db)
    now = dt.datetime.utcnow()
    data = {
        "range_30d": ledger.summary(db, now - dt.timedelta(days=days), now),
        "today": ledger.summary(db, now - dt.timedelta(days=1), now),
        "week": ledger.summary(db, now - dt.timedelta(days=7), now),
    }
    # top games/products
    from sqlalchemy import func
    top_products = db.query(models.OrderItem.title, func.sum(models.OrderItem.total_price))\
        .join(models.Order, models.Order.id == models.OrderItem.order_id)\
        .filter(models.Order.status == "COMPLETED").group_by(models.OrderItem.title)\
        .order_by(func.sum(models.OrderItem.total_price).desc()).limit(10).all()
    data["top_products"] = [{"title": t, "total": str(v)} for t, v in top_products]
    data["statuses"] = {k: v for k, v in
                        db.query(models.Order.status, func.count(models.Order.id)).group_by(models.Order.status).all()}
    data["switches"] = {"SALES_ENABLED": settings.SALES_ENABLED,
                        "SUPPLIER_ORDERS_ENABLED": settings.SUPPLIER_ORDERS_ENABLED,
                        "PAYMENTS_ENABLED": settings.PAYMENTS_ENABLED}
    for k, v in data.items():
        if isinstance(v, dict):
            data[k] = {kk: (str(vv) if isinstance(vv, Decimal) else vv) for kk, vv in v.items()}
    return data


# ---------- users ----------
@router.get("/users")
def users(request: Request, db: Db, search: str = "", page: int = 1, per_page: int = 20):
    require_admin(request, db)
    query = db.query(models.User)
    if search:
        query = query.filter((models.User.username.ilike(f"%{search}%")) |
                             (models.User.email.ilike(f"%{search}%")))
    total = query.count()
    items = query.order_by(models.User.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    from app.dependencies import user_roles
    return {"items": [{"id": u.id, "username": u.username, "email": u.email,
                       "banned": u.is_banned, "active": u.is_active,
                       "roles": sorted(user_roles(u))} for u in items], "total": total}


class BanIn(BaseModel):
    banned: bool


@router.post("/users/{user_id}/ban")
def ban_user(user_id: int, body: BanIn, request: Request, db: Db):
    admin = require_admin(request, db)
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user_not_found")
    old = u.is_banned
    u.is_banned = body.banned
    set_svc.audit(db, admin.id, "user_ban", "user", user_id, {"banned": old}, {"banned": body.banned}, _ip(request))
    db.commit()
    return {"ok": True}


# ---------- games ----------
class GameIn(BaseModel):
    name: str
    slug: str | None = None
    description: str = ""
    logo: str = ""
    cover: str = ""
    banner: str = ""
    category_id: int | None = None
    supplier_id: int | None = None
    status: str = "active"
    featured: bool = False


@router.get("/games")
def admin_games(request: Request, db: Db, page: int = 1, per_page: int = 50):
    require_admin(request, db)
    query = db.query(models.Game).order_by(models.Game.id)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"id": g.id, "name": g.name, "slug": g.slug, "status": g.status,
                       "featured": g.featured, "products": len(g.products)} for g in items], "total": total}


@router.post("/games")
def create_game(body: GameIn, request: Request, db: Db):
    admin = require_admin(request, db)
    slug = body.slug or "".join(c.lower() if c.isalnum() else "-" for c in body.name).strip("-")
    if db.query(models.Game).filter_by(slug=slug).first():
        raise HTTPException(status_code=400, detail="slug_exists")
    g = models.Game(name=body.name, slug=slug, description=body.description, logo=body.logo,
                    cover=body.cover, banner=body.banner, category_id=body.category_id,
                    supplier_id=body.supplier_id, status=body.status, featured=body.featured)
    db.add(g)
    db.flush()
    set_svc.audit(db, admin.id, "game_create", "game", g.id, {}, {"name": body.name}, _ip(request))
    db.commit()
    return {"ok": True, "id": g.id}


@router.patch("/games/{game_id}")
def update_game(game_id: int, body: GameIn, request: Request, db: Db):
    admin = require_admin(request, db)
    g = db.get(models.Game, game_id)
    if not g:
        raise HTTPException(status_code=404, detail="game_not_found")
    old = {"name": g.name, "status": g.status, "featured": g.featured}
    for f in ("name", "description", "logo", "cover", "banner", "status"):
        v = getattr(body, f)
        if v is not None:
            setattr(g, f, v)
    g.featured = body.featured
    if body.category_id is not None:
        g.category_id = body.category_id
    if body.supplier_id is not None:
        g.supplier_id = body.supplier_id
    set_svc.audit(db, admin.id, "game_update", "game", game_id, old, {"name": g.name}, _ip(request))
    db.commit()
    return {"ok": True}


# ---------- products + pricing ----------
class ProductPriceIn(BaseModel):
    customer_price: float
    supplier_cost: float | None = None
    override_loss_protection: bool = False


@router.get("/products")
def admin_products(request: Request, db: Db, game_id: int | None = None, search: str = "",
                   page: int = 1, per_page: int = 50):
    require_admin(request, db)
    query = db.query(models.Product)
    if game_id:
        query = query.filter_by(game_id=game_id)
    if search:
        query = query.filter(models.Product.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(models.Product.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    out = []
    for p in items:
        quote = quote_for_product(p, settings)
        out.append({"id": p.id, "name": p.name, "game": p.game.name if p.game else "",
                    "supplier_cost": str(p.supplier_cost), "price": str(p.customer_price),
                    "min_safe": str(quote["minimum_safe_price"]),
                    "suggested": str(quote["suggested_price"]),
                    "profit": str(quote["expected_profit"]),
                    "margin": str(quote["expected_margin_percent"]),
                    "status": p.status})
    return {"items": out, "total": total}


@router.get("/products/{product_id}/pricing")
def pricing_preview(product_id: int, request: Request, db: Db, new_price: float | None = None):
    require_admin(request, db)
    p = db.get(models.Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product_not_found")
    quote = quote_for_product(p, settings, new_price=new_price)
    allowed, warn = enforce_price(quote["new_price"] if new_price is not None else p.customer_price,
                                 quote, allow_override=False)
    quote["blocked"] = not allowed
    quote["warning"] = warn
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in quote.items()}


@router.post("/products/{product_id}/price")
def set_price(product_id: int, body: ProductPriceIn, request: Request, db: Db):
    admin = require_admin(request, db)
    p = db.get(models.Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="product_not_found")
    if body.supplier_cost is not None:
        p.supplier_cost = q(body.supplier_cost)
    quote = quote_for_product(p, settings, new_price=body.customer_price)
    allowed, warn = enforce_price(body.customer_price, quote,
                                 allow_override=body.override_loss_protection and settings.LOSS_SELLING is False)
    # override only when admin explicitly enables it per product AND global allows override flag
    if not allowed and not (body.override_loss_protection and p.override_loss_protection):
        if not allowed:
            # explicit per-request override requires the product flag to be enabled first
            raise HTTPException(status_code=400, detail=warn or "price_below_minimum")
    old = {"price": str(p.customer_price), "cost": str(p.supplier_cost)}
    p.customer_price = q(body.customer_price)
    if body.override_loss_protection:
        p.override_loss_protection = True
    set_svc.audit(db, admin.id, "price_change", "product", product_id, old,
                  {"price": str(p.customer_price), "override": body.override_loss_protection}, _ip(request))
    db.commit()
    return {"ok": True, "warning": warn}


# ---------- suppliers ----------
@router.get("/suppliers")
def suppliers(request: Request, db: Db):
    require_admin(request, db)
    items = db.query(models.Supplier).all()
    return {"items": [{"id": s.id, "name": s.name, "code": s.code, "adapter": s.adapter,
                       "configured": bool(s.api_url and s.api_key),
                       "active": s.is_active, "balance": str(s.balance),
                       "last_error": s.last_error} for s in items]}


class SupplierIn(BaseModel):
    name: str
    code: str
    adapter: str = "generic_http"
    api_url: str = ""
    api_key: str = ""
    is_active: bool = True


@router.post("/suppliers")
def upsert_supplier(body: SupplierIn, request: Request, db: Db):
    admin = require_admin(request, db)
    s = db.query(models.Supplier).filter_by(code=body.code).first()
    if not s:
        s = models.Supplier(name=body.name, code=body.code)
        db.add(s)
    s.name = body.name
    s.adapter = body.adapter
    s.api_url = body.api_url
    if body.api_key and body.api_key != "****":
        s.api_key = body.api_key
    s.is_active = body.is_active
    set_svc.audit(db, admin.id, "supplier_change", "supplier", s.code, {}, {"active": s.is_active}, _ip(request))
    db.commit()
    return {"ok": True, "id": s.id}


# ---------- orders ----------
@router.get("/orders")
def admin_orders(request: Request, db: Db, status: str = "", page: int = 1, per_page: int = 20):
    require_admin(request, db)
    query = db.query(models.Order).order_by(models.Order.id.desc())
    if status:
        query = query.filter_by(status=status)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"id": o.id, "public_id": o.public_id, "user": o.user_id, "kind": o.kind,
                       "status": o.status, "total": str(o.total),
                       "created_at": o.created_at.isoformat()} for o in items], "total": total}


class OrderStatusIn(BaseModel):
    status: str
    note: str = ""


@router.post("/orders/{order_id}/status")
def admin_order_status(order_id: int, body: OrderStatusIn, request: Request, db: Db):
    admin = require_admin(request, db)
    o = db.get(models.Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="order_not_found")
    old = o.status
    try:
        order_svc.set_status(o, body.status, body.note or "manual by admin")
    except order_svc.OrderError as e:
        raise HTTPException(status_code=400, detail=e.key)
    set_svc.audit(db, admin.id, "order_status", "order", order_id, {"status": old},
                  {"status": body.status}, _ip(request))
    if o.user_id:
        notify.create(db, o.user_id, "order_update", body.status, o.public_id, f"/orders/{o.public_id}")
    db.commit()
    return {"ok": True}


@router.get("/payments")
def admin_payments(request: Request, db: Db, page: int = 1, per_page: int = 20):
    require_admin(request, db)
    query = db.query(models.Payment).order_by(models.Payment.id.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"id": p.id, "order": p.order_id, "provider": p.provider,
                       "status": p.status, "amount": str(p.amount)} for p in items], "total": total}


# ---------- marketplace ----------
@router.get("/sellers")
def admin_sellers(request: Request, db: Db, status: str = ""):
    require_admin(request, db)
    query = db.query(models.Seller)
    if status:
        query = query.filter_by(status=status)
    return {"items": [{"id": s.id, "shop": s.shop_name, "slug": s.slug, "status": s.status,
                       "sales": s.sales_count} for s in query.all()]}


@router.post("/sellers/{seller_id}/verify")
def verify_seller(seller_id: int, request: Request, db: Db, approved: bool = True):
    admin = require_admin(request, db)
    s = db.get(models.Seller, seller_id)
    if not s:
        raise HTTPException(status_code=404, detail="not_found")
    old = s.status
    s.status = "approved" if approved else "rejected"
    set_svc.audit(db, admin.id, "seller_verification", "seller", seller_id,
                  {"status": old}, {"status": s.status}, _ip(request))
    db.commit()
    return {"ok": True}


@router.get("/payouts")
def admin_payouts(request: Request, db: Db, status: str = ""):
    require_admin(request, db)
    query = db.query(models.SellerPayout).order_by(models.SellerPayout.id.desc())
    if status:
        query = query.filter_by(status=status)
    return {"items": [{"id": p.id, "seller": p.seller_id, "amount": str(p.amount),
                       "method": p.method, "status": p.status} for p in query.all()]}


@router.post("/payouts/{payout_id}")
def decide_payout(payout_id: int, request: Request, db: Db, approve: bool = True):
    admin = require_admin(request, db)
    p = db.get(models.SellerPayout, payout_id)
    if not p or p.status != "pending":
        raise HTTPException(status_code=400, detail="invalid_payout")
    if approve:
        p.status = "approved"
        p.decided_by = admin.id
        ledger.record(db, "seller_payout", -q(p.amount), None, "UZS", f"payout {p.id}")
    else:
        p.status = "rejected"
        p.decided_by = admin.id
        from app.services import marketplace_svc as ms
        bal = ms.get_balance(db, p.seller_id)
        bal.available = q(bal.available) + q(p.amount)
    set_svc.audit(db, admin.id, "payout_decision", "payout", payout_id, {"status": "pending"},
                  {"status": p.status}, _ip(request))
    db.commit()
    return {"ok": True}


# ---------- donations / coupons / promotions ----------
class PresetIn(BaseModel):
    amount: float
    is_active: bool = True


@router.get("/donation-presets")
def get_presets(request: Request, db: Db):
    require_admin(request, db)
    items = db.query(models.DonationPreset).order_by(models.DonationPreset.sort_order).all()
    return {"items": [{"id": p.id, "amount": str(p.amount), "active": p.is_active} for p in items]}


@router.post("/donation-presets")
def add_preset(body: PresetIn, request: Request, db: Db):
    admin = require_admin(request, db)
    p = models.DonationPreset(amount=q(body.amount), is_active=body.is_active)
    db.add(p)
    set_svc.audit(db, admin.id, "preset_add", "donation_preset", "", {}, {"amount": str(body.amount)}, _ip(request))
    db.commit()
    return {"ok": True, "id": p.id}


class CouponIn(BaseModel):
    code: str
    kind: str = "percent"
    value: float = 0
    min_order: float = 0
    usage_limit: int = 0
    per_user_limit: int = 1
    is_active: bool = True


@router.get("/coupons")
def get_coupons(request: Request, db: Db):
    require_admin(request, db)
    items = db.query(models.Coupon).order_by(models.Coupon.id.desc()).all()
    return {"items": [{"id": c.id, "code": c.code, "kind": c.kind, "value": str(c.value),
                       "used": c.used_count, "active": c.is_active} for c in items]}


@router.post("/coupons")
def upsert_coupon(body: CouponIn, request: Request, db: Db):
    admin = require_admin(request, db)
    code = body.code.strip().upper()
    c = db.query(models.Coupon).filter_by(code=code).first()
    if not c:
        c = models.Coupon(code=code)
        db.add(c)
    c.kind = body.kind
    c.value = q(body.value)
    c.min_order = q(body.min_order)
    c.usage_limit = body.usage_limit
    c.per_user_limit = body.per_user_limit
    c.is_active = body.is_active
    set_svc.audit(db, admin.id, "coupon_change", "coupon", code, {}, {"value": str(body.value)}, _ip(request))
    db.commit()
    return {"ok": True, "id": c.id}


class PromoIn(BaseModel):
    title: str
    slug: str | None = None
    description: str = ""
    banner: str = ""
    target_url: str = ""
    is_active: bool = True


@router.get("/promotions")
def get_promos(request: Request, db: Db):
    require_admin(request, db)
    items = db.query(models.Promotion).order_by(models.Promotion.sort_order).all()
    return {"items": [{"id": p.id, "title": p.title, "slug": p.slug, "banner": p.banner,
                       "active": p.is_active} for p in items]}


@router.post("/promotions")
def upsert_promo(body: PromoIn, request: Request, db: Db):
    admin = require_admin(request, db)
    slug = body.slug or "".join(c.lower() if c.isalnum() else "-" for c in body.title).strip("-")
    p = db.query(models.Promotion).filter_by(slug=slug).first()
    if not p:
        p = models.Promotion(title=body.title, slug=slug)
        db.add(p)
    p.title = body.title
    p.description = body.description
    p.banner = body.banner
    p.target_url = body.target_url
    p.is_active = body.is_active
    set_svc.audit(db, admin.id, "promotion_change", "promotion", slug, {}, {"title": body.title}, _ip(request))
    db.commit()
    return {"ok": True, "id": p.id}


# ---------- media / support / audit / settings ----------
@router.get("/media")
def get_media(request: Request, db: Db, page: int = 1, per_page: int = 40):
    require_admin(request, db)
    query = db.query(models.Media).order_by(models.Media.id.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"id": m.id, "file": m.filename, "path": m.path, "type": m.type,
                       "size": m.size} for m in items], "total": total}


@router.post("/media-upload")
async def upload_media(request: Request, db: Db):
    admin = require_admin(request, db)
    form = await request.form()
    file = form.get("file")
    media_type = str(form.get("type") or "PRODUCT_IMAGE")
    if not file or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="invalid_file_type")
    content = await file.read()
    from app.services import media_svc
    try:
        row = media_svc.save_upload(db, file.filename or "upload", content,
                                    file.content_type or "", media_type=media_type,
                                    uploaded_by=admin.id)
    except media_svc.MediaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    set_svc.audit(db, admin.id, "media_upload", "media", row.id, {}, {"path": row.path}, _ip(request))
    db.commit()
    return {"ok": True, "id": row.id, "path": row.path}


@router.delete("/media/{media_id}")
def delete_media(media_id: int, request: Request, db: Db):
    admin = require_admin(request, db)
    m = db.get(models.Media, media_id)
    if not m:
        raise HTTPException(status_code=404, detail="not_found")
    set_svc.audit(db, admin.id, "media_delete", "media", media_id, {"path": m.path}, {}, _ip(request))
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/tickets")
def admin_tickets(request: Request, db: Db, status: str = ""):
    require_admin(request, db)
    query = db.query(models.SupportTicket).order_by(models.SupportTicket.id.desc())
    if status:
        query = query.filter_by(status=status)
    return {"items": [{"id": t.id, "user": t.user_id, "subject": t.subject,
                       "status": t.status, "category": t.category} for t in query.limit(100).all()]}


class TicketStatusIn(BaseModel):
    status: str


@router.post("/tickets/{ticket_id}/status")
def admin_ticket_status(ticket_id: int, body: TicketStatusIn, request: Request, db: Db):
    admin = require_admin(request, db)
    t = db.get(models.SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="not_found")
    t.status = body.status
    set_svc.audit(db, admin.id, "ticket_status", "ticket", ticket_id, {}, {"status": body.status}, _ip(request))
    db.commit()
    return {"ok": True}


@router.get("/audit")
def get_audit(request: Request, db: Db, page: int = 1, per_page: int = 50):
    require_admin(request, db)
    query = db.query(models.AuditLog).order_by(models.AuditLog.id.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"id": a.id, "admin": a.admin_id, "action": a.action, "entity": a.entity,
                       "entity_id": a.entity_id, "ip": a.ip,
                       "created_at": a.created_at.isoformat()} for a in items], "total": total}


@router.get("/settings")
def get_settings_all(request: Request, db: Db):
    require_admin(request, db)
    items = db.query(models.Setting).all()
    return {"items": [{"key": s.key, "value": s.value, "description": s.description} for s in items],
            "env": {"SALES_ENABLED": settings.SALES_ENABLED, "LOSS_SELLING": settings.LOSS_SELLING}}


class SettingIn(BaseModel):
    key: str
    value: str


@router.post("/settings")
def set_setting(body: SettingIn, request: Request, db: Db):
    admin = require_admin(request, db)
    old = set_svc.get_setting(db, body.key, "")
    set_svc.set_setting(db, body.key, body.value)
    set_svc.audit(db, admin.id, "setting_change", "setting", body.key, {"value": old},
                  {"value": body.value}, _ip(request))
    db.commit()
    return {"ok": True}


@router.post("/refunds/{order_id}")
def create_refund(order_id: int, request: Request, db: Db, amount: float = 0, reason: str = ""):
    admin = require_admin(request, db)
    o = db.get(models.Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="order_not_found")
    amt = q(amount) if amount else q(o.total)
    r = models.Refund(order_id=o.id, amount=amt, reason=reason[:500], status="approved", decided_by=admin.id)
    db.add(r)
    try:
        order_svc.set_status(o, "REFUND_PENDING", reason)
        order_svc.set_status(o, "REFUNDED", "refund approved")
    except order_svc.OrderError:
        pass
    ledger.record(db, "refund", -amt, o.id, o.currency, reason)
    if o.user_id:
        wallet_svc.credit_refund(db, o.user_id, amt, reference=o.public_id)
        notify.create(db, o.user_id, "refund", "refund_issued", o.public_id, f"/orders/{o.public_id}")
    set_svc.audit(db, admin.id, "refund", "order", order_id, {}, {"amount": str(amt)}, _ip(request))
    db.commit()
    return {"ok": True}
