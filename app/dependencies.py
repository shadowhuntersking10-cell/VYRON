"""Shared FastAPI dependencies (re-exported for a stable import path)."""
from app.auth.deps import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_roles,
    require_seller,
    require_user,
)

__all__ = [
    "get_current_user",
    "get_current_user_optional",
    "require_admin",
    "require_roles",
    "require_seller",
    "require_user",
]
