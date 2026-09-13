"""Pricing engine, media v2, FX snapshots, presets, categories, game fields.

Revision ID: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    try:
        op.add_column(table, column)
    except Exception:
        # Idempotent: column may already exist via ensure_schema().
        pass


def upgrade() -> None:
    pricing_cols = lambda: [  # noqa: E731
        sa.Column("payment_fee_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("payment_fixed_fee", sa.Numeric(18, 2), nullable=True),
        sa.Column("platform_margin_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("platform_fixed_fee", sa.Numeric(18, 2), nullable=True),
        sa.Column("tax_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("minimum_margin_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("maximum_discount_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("loss_leader_allowed", sa.Boolean(), nullable=False, server_default="0"),
    ]
    for col in pricing_cols():
        _add("products", col)
    _add("products", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="0"))
    for col in pricing_cols():
        _add("product_variants", col)

    _add("games", sa.Column("cover_url", sa.String(512), nullable=True))
    _add("games", sa.Column("accent_color", sa.String(16), nullable=True))
    _add("games", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="0"))

    _add("media_files", sa.Column("media_type", sa.String(32), nullable=False, server_default="PRODUCT_IMAGE"))
    _add("media_files", sa.Column("alt_text", sa.String(255), nullable=True))
    _add("media_files", sa.Column("game_id", sa.Integer(), nullable=True))
    _add("media_files", sa.Column("product_id", sa.Integer(), nullable=True))

    _add("donation_profiles", sa.Column("display_name", sa.String(128), nullable=True))
    _add("donation_profiles", sa.Column("cover_url", sa.String(512), nullable=True))

    _add("orders", sa.Column("fx_base_currency", sa.String(8), nullable=False, server_default="UZS"))
    _add("orders", sa.Column("fx_rate", sa.Numeric(18, 6), nullable=True))
    _add("orders", sa.Column("fx_quoted_at", sa.DateTime(timezone=True), nullable=True))

    _add("marketplace_listings", sa.Column("category_id", sa.Integer(),
                                           sa.ForeignKey("marketplace_categories.id", ondelete="SET NULL"),
                                           nullable=True))

    op.create_table(
        "game_fields",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label_uz", sa.String(128), nullable=False),
        sa.Column("label_en", sa.String(128), nullable=False),
        sa.Column("label_ru", sa.String(128), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("game_id", "key", name="ix_game_fields_unique"),
    )
    op.create_table(
        "donation_presets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="UZS", index=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("currency", "amount", name="ix_donation_presets_unique"),
    )
    op.create_table(
        "marketplace_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name_uz", sa.String(128), nullable=False),
        sa.Column("name_en", sa.String(128), nullable=False),
        sa.Column("name_ru", sa.String(128), nullable=False),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("icon", sa.String(64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "marketplace_listing_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("media_id", sa.Integer(), sa.ForeignKey("media_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("alt_text", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for table in ("marketplace_listing_images", "marketplace_categories", "donation_presets", "game_fields"):
        try:
            op.drop_table(table)
        except Exception:
            pass
    _pricing = ["payment_fee_percent", "payment_fixed_fee", "platform_margin_percent",
                "platform_fixed_fee", "tax_percent", "minimum_margin_percent",
                "maximum_discount_percent", "loss_leader_allowed"]
    cols = ([("marketplace_listings", "category_id"), ("marketplace_categories", "icon")]
            + [("orders", c) for c in ("fx_quoted_at", "fx_rate", "fx_base_currency")]
            + [("donation_profiles", c) for c in ("cover_url", "display_name")]
            + [("media_files", c) for c in ("product_id", "game_id", "alt_text", "media_type")]
            + [("games", c) for c in ("is_demo", "accent_color", "cover_url")]
            + [("products", c) for c in (["is_demo"] + _pricing)]
            + [("product_variants", c) for c in _pricing])
    for table, col in cols:
        try:
            op.drop_column(table, col)
        except Exception:
            pass
    for table in ("products", "product_variants"):
        for col in ("payment_fee_percent", "payment_fixed_fee", "platform_margin_percent",
                    "platform_fixed_fee", "tax_percent", "minimum_margin_percent",
                    "maximum_discount_percent", "loss_leader_allowed"):
            try:
                op.drop_column(table, col)
            except Exception:
                pass
