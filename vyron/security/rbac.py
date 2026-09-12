"""Role-based access control.

Roles: USER, SELLER, SUPPORT, MODERATOR, FINANCE, ADMIN, SUPER_ADMIN.
Every protected endpoint verifies authorization SERVER-SIDE via these
dependencies. Frontend visibility is cosmetic only.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import get_db
from vyron.db.models import User
from vyron.enums import ROLE_LEVELS, UserRole
from vyron.errors import AuthError, ForbiddenError
from vyron.security.sessions import get_session_user


def get_current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    user = get_session_user(db, request)
    if user is None:
        raise AuthError()
    return user


def get_optional_user(request: Request, db: DbSession = Depends(get_db)) -> Optional[User]:
    return get_session_user(db, request)


def role_at_least(user: User, minimum: UserRole) -> bool:
    return ROLE_LEVELS.get(UserRole(user.role), 0) >= ROLE_LEVELS[minimum]


def user_has_role(user: User, roles: Iterable[UserRole]) -> bool:
    return UserRole(user.role) in set(roles)


def require_roles(*roles: UserRole, min_level: Optional[UserRole] = None) -> Callable[..., User]:
    """FastAPI dependency factory: allow if user has any of `roles`
    or (when given) at least `min_level` privilege."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if min_level is not None and role_at_least(user, min_level):
            return user
        if roles and user_has_role(user, roles):
            return user
        raise ForbiddenError()

    return dependency


require_staff = require_roles(min_level=UserRole.SUPPORT)
require_moderator = require_roles(min_level=UserRole.MODERATOR)
require_finance = require_roles(UserRole.FINANCE, UserRole.ADMIN, UserRole.SUPER_ADMIN)
require_admin = require_roles(min_level=UserRole.ADMIN)
require_super_admin = require_roles(UserRole.SUPER_ADMIN)
