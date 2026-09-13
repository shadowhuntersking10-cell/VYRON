from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.dependencies import get_current_admin_user
from app.models.models import (
    User, Game, Product, Order, Payment, Seller, DonationProfile,
    RevenueLedger, AuditLog, GameCategory, Supplier, Coupon, Promotion,
    Media, MarketplaceCategory, MarketplaceListing
)
from app.services.pricing import PricingService
from typing import Optional
from decimal import Decimal
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/dashboard")
async def admin_dashboard(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    # Basic metrics
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # Orders
    total_orders = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    today_orders = (await db.execute(select(func.count(Order.id)).where(Order.created_at >= today_start))).scalar() or 0
    paid_orders = (await db.execute(select(func.count(Order.id)).where(Order.status == "PAID"))).scalar() or 0

    # Revenue
    gross_result = await db.execute(select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.status.in_(["PAID", "COMPLETED"])))
    gross_revenue = gross_result.scalar() or Decimal("0.00")

    # Users
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    today_users = (await db.execute(select(func.count(User.id)).where(User.created_at >= today_start))).scalar() or 0

    # Products
    total_products = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    total_games = (await db.execute(select(func.count(Game.id)))).scalar() or 0

    # Revenue ledger
    net_result = await db.execute(select(func.coalesce(func.sum(RevenueLedger.net_revenue), 0)))
    net_revenue = net_result.scalar() or Decimal("0.00")

    # Top games
    top_games_result = await db.execute(
        select(Game.name, func.count(Order.id).label("cnt"))
        .join(Product, Product.game_id == Game.id)
        .join(Order, Order.id == Product.id)  # simplified, real would join order_items
        .group_by(Game.id)
        .limit(5)
    )
    # Actually better to get top by product count
    top_games_q = await db.execute(select(Game).where(Game.featured == True).limit(5))
    top_games = top_games_q.scalars().all()

    return {
        "metrics": {
            "total_orders": total_orders,
            "today_orders": today_orders,
            "paid_orders": paid_orders,
            "gross_revenue": float(gross_revenue),
            "net_revenue": float(net_revenue),
            "total_users": total_users,
            "today_users": today_users,
            "total_products": total_products,
            "total_games": total_games
        },
        "top_games": [{"id": g.id, "name": g.name, "slug": g.slug} for g in top_games],
        "sales_enabled": True,
        "payments_enabled": True
    }

@router.get("/users")
async def list_users_admin(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    query = select(User)
    if search:
        query = query.where(User.username.ilike(f"%{search}%") | User.email.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(User.created_at.desc()).offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "items": [{"id": u.id, "username": u.username, "email": u.email, "is_admin": u.is_admin, "status": u.status, "created_at": u.created_at.isoformat()} for u in users],
        "total": total,
        "page": page,
        "per_page": per_page
    }

@router.get("/orders")
async def list_orders_admin(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    query = select(Order)
    if status:
        query = query.where(Order.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(Order.created_at.desc()).offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    orders = result.scalars().all()

    return {
        "items": [{"id": o.id, "order_number": o.order_number, "user_id": o.user_id, "status": o.status, "total_amount": float(o.total_amount), "created_at": o.created_at.isoformat()} for o in orders],
        "total": total,
        "page": page,
        "per_page": per_page
    }

@router.get("/games")
async def list_games_admin(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    result = await db.execute(select(Game).order_by(Game.sort_order))
    games = result.scalars().all()
    return [{"id": g.id, "name": g.name, "slug": g.slug, "status": g.status, "featured": g.featured, "logo_url": g.logo_url} for g in games]

@router.post("/games")
async def create_game_admin(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    # Validate slug unique
    result = await db.execute(select(Game).where(Game.slug == payload.get("slug")))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already exists")

    game = Game(
        name=payload.get("name"),
        slug=payload.get("slug"),
        description=payload.get("description"),
        short_description=payload.get("short_description"),
        logo_url=payload.get("logo_url"),
        cover_url=payload.get("cover_url"),
        banner_url=payload.get("banner_url"),
        category_id=payload.get("category_id"),
        status=payload.get("status", "ACTIVE"),
        featured=payload.get("featured", False),
        popular=payload.get("popular", False),
        sort_order=payload.get("sort_order", 0)
    )
    db.add(game)
    await db.flush()

    # Audit log
    from app.models.models import AuditLog
    log = AuditLog(
        admin_id=current_admin.id,
        action="CREATE_GAME",
        entity_type="GAME",
        entity_id=game.id,
        new_value=payload
    )
    db.add(log)
    await db.commit()

    return {"success": True, "id": game.id}

@router.put("/games/{game_id}")
async def update_game_admin(
    game_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    result = await db.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    old = {"name": game.name, "status": game.status, "featured": game.featured}

    for key in ["name", "slug", "description", "short_description", "logo_url", "cover_url", "banner_url", "status", "featured", "popular", "sort_order", "category_id"]:
        if key in payload:
            setattr(game, key, payload[key])

    from app.models.models import AuditLog
    log = AuditLog(
        admin_id=current_admin.id,
        action="UPDATE_GAME",
        entity_type="GAME",
        entity_id=game.id,
        old_value=old,
        new_value=payload
    )
    db.add(log)
    await db.commit()

    return {"success": True}

@router.get("/products")
async def list_products_admin(
    game_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    query = select(Product)
    if game_id:
        query = query.where(Product.game_id == game_id)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(Product.created_at.desc()).offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    products = result.scalars().all()

    items = []
    for p in products:
        pricing = PricingService.calculate_product_pricing(p.supplier_cost)
        items.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "game_id": p.game_id,
            "supplier_cost": float(p.supplier_cost),
            "customer_price": float(p.customer_price),
            "minimum_safe_price": float(pricing["minimum_safe_price"]),
            "suggested_price": float(pricing["suggested_price"]),
            "expected_profit": float(pricing["expected_profit"]),
            "is_active": p.is_active,
            "featured": p.featured
        })

    return {"items": items, "total": total, "page": page, "per_page": per_page}

@router.post("/products")
async def create_product_admin(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    # Validate pricing
    supplier_cost = Decimal(str(payload.get("supplier_cost", "0")))
    customer_price = Decimal(str(payload.get("customer_price", "0")))

    validation = PricingService.validate_price(supplier_cost, customer_price)
    if validation["is_loss"] and not payload.get("force_loss", False):
        raise HTTPException(status_code=400, detail=f"Price below minimum safe price {validation['minimum_safe_price']}. Loss selling is blocked.")

    product = Product(
        name=payload.get("name"),
        slug=payload.get("slug"),
        description=payload.get("description"),
        game_id=payload.get("game_id"),
        supplier_cost=supplier_cost,
        customer_price=customer_price,
        old_price=Decimal(str(payload["old_price"])) if payload.get("old_price") else None,
        currency=payload.get("currency", "UZS"),
        image_url=payload.get("image_url"),
        featured=payload.get("featured", False),
        popular=payload.get("popular", False),
        is_active=payload.get("is_active", True),
        supplier_id=payload.get("supplier_id"),
        supplier_product_id=payload.get("supplier_product_id")
    )
    db.add(product)
    await db.flush()

    from app.models.models import AuditLog
    log = AuditLog(
        admin_id=current_admin.id,
        action="CREATE_PRODUCT",
        entity_type="PRODUCT",
        entity_id=product.id,
        new_value=payload
    )
    db.add(log)
    await db.commit()

    return {"success": True, "id": product.id, "pricing": validation}

@router.put("/products/{product_id}")
async def update_product_admin(
    product_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    old_price = product.customer_price
    old_cost = product.supplier_cost

    # Check pricing if price changed
    new_cost = Decimal(str(payload.get("supplier_cost", product.supplier_cost)))
    new_price = Decimal(str(payload.get("customer_price", product.customer_price)))

    if new_cost != product.supplier_cost or new_price != product.customer_price:
        validation = PricingService.validate_price(new_cost, new_price)
        if validation["is_loss"] and not payload.get("force_loss", False):
            raise HTTPException(status_code=400, detail=f"Price below minimum safe price {validation['minimum_safe_price']}")

    for key in ["name", "slug", "description", "game_id", "currency", "image_url", "featured", "popular", "is_active", "supplier_id", "supplier_product_id", "old_price"]:
        if key in payload:
            val = payload[key]
            if key in ("old_price",) and val is not None:
                val = Decimal(str(val))
            setattr(product, key, val)

    product.supplier_cost = new_cost
    product.customer_price = new_price

    from app.models.models import AuditLog
    log = AuditLog(
        admin_id=current_admin.id,
        action="UPDATE_PRODUCT",
        entity_type="PRODUCT",
        entity_id=product.id,
        old_value={"customer_price": float(old_price), "supplier_cost": float(old_cost)},
        new_value={"customer_price": float(new_price), "supplier_cost": float(new_cost)}
    )
    db.add(log)
    await db.commit()

    return {"success": True, "pricing": PricingService.validate_price(new_cost, new_price)}

@router.get("/revenue")
async def revenue_admin(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    since = datetime.utcnow() - timedelta(days=days)
    
    # Gross
    gross_q = await db.execute(select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.created_at >= since, Order.status.in_(["PAID", "COMPLETED"])))
    gross = gross_q.scalar() or Decimal("0.00")

    # Net from ledger
    net_q = await db.execute(select(func.coalesce(func.sum(RevenueLedger.net_revenue), 0)).where(RevenueLedger.created_at >= since))
    net = net_q.scalar() or Decimal("0.00")

    # Daily breakdown
    daily = []
    for i in range(days):
        day = since + timedelta(days=i)
        next_day = day + timedelta(days=1)
        day_gross_q = await db.execute(select(func.coalesce(func.sum(Order.total_amount), 0)).where(Order.created_at >= day, Order.created_at < next_day, Order.status.in_(["PAID", "COMPLETED"])))
        day_gross = day_gross_q.scalar() or Decimal("0.00")
        daily.append({"date": day.date().isoformat(), "gross": float(day_gross)})

    return {
        "period_days": days,
        "gross_revenue": float(gross),
        "net_revenue": float(net),
        "daily": daily
    }

@router.get("/audit-logs")
async def audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [{"id": l.id, "admin_id": l.admin_id, "action": l.action, "entity_type": l.entity_type, "entity_id": l.entity_id, "created_at": l.created_at.isoformat()} for l in logs],
        "total": total,
        "page": page,
        "per_page": per_page
    }

@router.get("/pricing/preview")
async def pricing_preview(
    supplier_cost: float,
    customer_price: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    cost = Decimal(str(supplier_cost))
    if customer_price is not None:
        price = Decimal(str(customer_price))
        validation = PricingService.validate_price(cost, price)
        return validation
    else:
        pricing = PricingService.calculate_product_pricing(cost)
        return pricing
