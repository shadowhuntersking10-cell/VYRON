"""Marketplace helpers: commission resolution, seller balances."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.services.pricing import q
from app.services.settings_service import get_setting


def commission_percent(db: Session, seller: models.Seller | None,
                       category: models.MarketplaceCategory | None,
                       global_default) -> Decimal:
    """Seller-specific > category > global."""
    if seller is not None and q(seller.commission_percent) > 0:
        return q(seller.commission_percent)
    if category is not None and q(category.commission_percent) > 0:
        return q(category.commission_percent)
    return q(global_default)


def split_sale(total, commission_pct) -> tuple[Decimal, Decimal]:
    """Returns (platform_commission, seller_net)."""
    total = q(total)
    commission = (total * q(commission_pct) / 100).quantize(Decimal("0.01"))
    return commission, (total - commission).quantize(Decimal("0.01"))


def get_balance(db: Session, seller_id: int) -> models.SellerBalance:
    bal = db.query(models.SellerBalance).filter_by(seller_id=seller_id).first()
    if not bal:
        bal = models.SellerBalance(seller_id=seller_id)
        db.add(bal)
        db.flush()
    return bal


def credit_sale(db: Session, seller_id: int, net_amount) -> None:
    bal = get_balance(db, seller_id)
    bal.pending = q(bal.pending) + q(net_amount)
    bal.lifetime_earned = q(bal.lifetime_earned) + q(net_amount)
    db.flush()
