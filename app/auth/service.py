from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import User, UserSession, Role, UserRole, TelegramUser
from app.utils.security import hash_password, verify_password, generate_session_token, validate_password_strength
from app.utils.helpers import validate_username
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class AuthService:
    @staticmethod
    async def register(
        db: AsyncSession,
        username: str,
        email: str,
        password: str,
        display_name: Optional[str] = None,
        language: str = "uz"
    ) -> tuple[bool, str, Optional[User]]:
        # Validate username
        valid, msg = validate_username(username)
        if not valid:
            return False, msg, None
        
        # Validate password
        strong, msg = validate_password_strength(password)
        if not strong:
            return False, msg, None

        # Check duplicate username
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            return False, "Username already exists", None

        # Check duplicate email
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            return False, "Email already exists", None

        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            display_name=display_name or username,
            language=language,
            status="ACTIVE",
            is_verified=False
        )
        db.add(user)
        await db.flush()

        # Create wallet
        from app.models.models import Wallet
        wallet = Wallet(user_id=user.id, balance=0, currency="UZS")
        db.add(wallet)

        # Assign default role
        result = await db.execute(select(Role).where(Role.name == "user"))
        role = result.scalar_one_or_none()
        if not role:
            role = Role(name="user", description="Regular user")
            db.add(role)
            await db.flush()
        
        user_role = UserRole(user_id=user.id, role_id=role.id)
        db.add(user_role)

        await db.commit()
        await db.refresh(user)
        logger.info(f"User registered: {username} ({email})")
        return True, "Registration successful", user

    @staticmethod
    async def login(
        db: AsyncSession,
        email_or_username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        remember_me: bool = False
    ) -> tuple[bool, str, Optional[User], Optional[str]]:
        # Find user by email or username
        result = await db.execute(
            select(User).where(
                (User.email == email_or_username) | (User.username == email_or_username)
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            return False, "Invalid credentials", None, None

        if user.status == "BANNED":
            return False, "Account is banned", None, None

        if not verify_password(password, user.password_hash):
            return False, "Invalid password", None, None

        # Create session
        token = generate_session_token()
        expires_days = 30 if remember_me else 7
        expires_at = datetime.utcnow() + timedelta(days=expires_days)

        session = UserSession(
            user_id=user.id,
            session_token=token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            is_valid=True
        )
        db.add(session)
        
        user.last_login_at = datetime.utcnow()
        await db.commit()

        logger.info(f"User logged in: {user.username}")
        return True, "Login successful", user, token

    @staticmethod
    async def logout(db: AsyncSession, session_token: str) -> bool:
        result = await db.execute(select(UserSession).where(UserSession.session_token == session_token))
        session = result.scalar_one_or_none()
        if session:
            session.is_valid = False
            await db.commit()
            return True
        return False

    @staticmethod
    async def get_user_by_session(db: AsyncSession, session_token: str) -> Optional[User]:
        result = await db.execute(
            select(UserSession).where(
                UserSession.session_token == session_token,
                UserSession.is_valid == True,
                UserSession.expires_at > datetime.utcnow()
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return None
        
        result = await db.execute(select(User).where(User.id == session.user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def link_telegram_user(
        db: AsyncSession,
        telegram_id: int,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> TelegramUser:
        result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
        tg_user = result.scalar_one_or_none()
        
        if tg_user:
            tg_user.user_id = user_id
            tg_user.username = username
            tg_user.first_name = first_name
            tg_user.last_name = last_name
        else:
            tg_user = TelegramUser(
                telegram_id=telegram_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=language_code
            )
            db.add(tg_user)
        
        # Check admin
        if telegram_id in settings.admin_telegram_ids_list:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.is_admin = True
                # Ensure admin role
                result = await db.execute(select(Role).where(Role.name == "admin"))
                admin_role = result.scalar_one_or_none()
                if not admin_role:
                    admin_role = Role(name="admin", description="Administrator")
                    db.add(admin_role)
                    await db.flush()
                
                result = await db.execute(select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == admin_role.id))
                if not result.scalar_one_or_none():
                    db.add(UserRole(user_id=user_id, role_id=admin_role.id))
        
        await db.commit()
        await db.refresh(tg_user)
        return tg_user
