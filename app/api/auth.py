from __future__ import annotations
from fastapi import APIRouter, Depends, Request, Response, Form, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.service import AuthService
from app.dependencies import get_current_user, get_current_user_optional
from app.models.models import User
from app.config import settings
from app.utils.security import verify_telegram_init_data
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
templates = Jinja2Templates(directory="templates")

@router.post("/register")
async def register_api(
    request: Request,
    response: Response,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    display_name: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    if password != password_confirm:
        if request.headers.get("accept", "").find("application/json") != -1:
            return JSONResponse({"success": False, "message": "Passwords do not match"}, status_code=400)
        return templates.TemplateResponse(request, "auth/register.html", {
            "error": "Passwords do not match",
            "username": username,
            "email": email
        }, status_code=400)

    success, message, user = await AuthService.register(
        db, username, email, password, display_name, language="uz"
    )

    if not success:
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse({"success": False, "message": message}, status_code=400)
        return templates.TemplateResponse(request, "auth/register.html", {
            "error": message,
            "username": username,
            "email": email
        }, status_code=400)

    # Auto login after registration
    success_login, msg, user, token = await AuthService.login(
        db, email, password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    if success_login and token:
        response = RedirectResponse(url="/profile", status_code=302)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=not settings.is_development,
            samesite="lax",
            max_age=30*24*60*60
        )
        return response

    return RedirectResponse(url="/login?registered=1", status_code=302)

@router.post("/login")
async def login_api(
    request: Request,
    email_or_username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    db: AsyncSession = Depends(get_db)
):
    success, message, user, token = await AuthService.login(
        db, email_or_username, password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        remember_me=remember_me
    )

    wants_json = "application/json" in request.headers.get("accept", "") or request.headers.get("content-type") == "application/json"

    if not success:
        if wants_json:
            return JSONResponse({"success": False, "message": message}, status_code=401)
        return templates.TemplateResponse(request, "auth/login.html", {
            "error": message,
            "email_or_username": email_or_username
        }, status_code=401)

    if wants_json:
        resp = JSONResponse({"success": True, "message": message, "token": token})
    else:
        resp = RedirectResponse(url="/", status_code=302)
    
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=not settings.is_development,
        samesite="lax",
        max_age=(30*24*60*60 if remember_me else 7*24*60*60)
    )
    return resp

@router.post("/logout")
@router.get("/logout")
async def logout_api(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional)
):
    token = request.cookies.get("session_token")
    if token:
        await AuthService.logout(db, token)
    
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response

@router.post("/telegram")
async def telegram_auth_api(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    try:
        body = await request.json()
        init_data = body.get("initData") or body.get("init_data") or ""
    except:
        form = await request.form()
        init_data = form.get("initData") or form.get("init_data") or ""

    if not init_data:
        return JSONResponse({"success": False, "message": "Missing initData"}, status_code=400)

    if not settings.TELEGRAM_BOT_TOKEN:
        return JSONResponse({"success": False, "message": "Telegram bot not configured"}, status_code=500)

    is_valid, user_data, error = verify_telegram_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)

    if not is_valid:
        return JSONResponse({"success": False, "message": f"Invalid Telegram auth: {error}"}, status_code=401)

    telegram_id = user_data.get("id")
    if not telegram_id:
        return JSONResponse({"success": False, "message": "Invalid user data"}, status_code=400)

    # Find or create user linked to telegram
    from sqlalchemy import select
    from app.models.models import TelegramUser, User

    result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
    tg_user = result.scalar_one_or_none()

    if tg_user and tg_user.user_id:
        result = await db.execute(select(User).where(User.id == tg_user.user_id))
        user = result.scalar_one_or_none()
        if user:
            # Create session
            from app.auth.service import AuthService
            from datetime import datetime, timedelta
            from app.models.models import UserSession
            from app.utils.security import generate_session_token
            
            token = generate_session_token()
            session = UserSession(
                user_id=user.id,
                session_token=token,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                expires_at=datetime.utcnow() + timedelta(days=30),
                is_valid=True
            )
            db.add(session)
            await db.commit()

            # Check admin
            if telegram_id in settings.admin_telegram_ids_list:
                user.is_admin = True
                await db.commit()

            resp = JSONResponse({
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "is_admin": user.is_admin
                },
                "token": token
            })
            resp.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=30*24*60*60)
            return resp

    # If no linked user, create a new user based on telegram data
    username = user_data.get("username") or f"tg_{telegram_id}"
    # Ensure unique username
    from sqlalchemy import select
    base_username = username
    counter = 1
    while True:
        result = await db.execute(select(User).where(User.username == username))
        if not result.scalar_one_or_none():
            break
        username = f"{base_username}_{counter}"
        counter += 1

    # Create user with random password (telegram users don't need password, but we create one)
    import secrets
    random_password = secrets.token_urlsafe(16)
    success, msg, new_user = await AuthService.register(
        db, username, f"{telegram_id}@telegram.vyron.uz", random_password,
        display_name=user_data.get("first_name") or username,
        language=user_data.get("language_code") or "uz"
    )

    if not success and "exists" in msg.lower():
        # Try to find existing user with that telegram email
        result = await db.execute(select(User).where(User.email == f"{telegram_id}@telegram.vyron.uz"))
        new_user = result.scalar_one_or_none()
        if not new_user:
            return JSONResponse({"success": False, "message": msg}, status_code=400)

    if not new_user:
        return JSONResponse({"success": False, "message": "Failed to create user"}, status_code=500)

    # Link telegram
    await AuthService.link_telegram_user(
        db, telegram_id, new_user.id,
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        language_code=user_data.get("language_code")
    )

    # Create session
    from datetime import datetime, timedelta
    from app.models.models import UserSession
    from app.utils.security import generate_session_token
    token = generate_session_token()
    session = UserSession(
        user_id=new_user.id,
        session_token=token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        expires_at=datetime.utcnow() + timedelta(days=30),
        is_valid=True
    )
    db.add(session)
    await db.commit()

    resp = JSONResponse({
        "success": True,
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "is_admin": new_user.is_admin
        },
        "token": token
    })
    resp.set_cookie("session_token", token, httponly=True, samesite="lax", max_age=30*24*60*60)
    return resp
