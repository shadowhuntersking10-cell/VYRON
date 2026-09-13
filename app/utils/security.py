from __future__ import annotations
import secrets
import hashlib
import hmac
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)

def generate_session_token() -> str:
    return secrets.token_urlsafe(64)

def create_jwt_token(data: dict, expires_minutes: int = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes or settings.JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.APP_SECRET, algorithm=settings.JWT_ALGORITHM)

def decode_jwt_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.APP_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None

def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if len(password) > 128:
        return False, "Password is too long"
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in password)
    if not (has_upper and has_lower and has_digit):
        return False, "Password must contain uppercase, lowercase and digit"
    if not has_special:
        # allow but warn? require for strong
        pass
    # check common patterns
    common = ["password", "123456", "qwerty"]
    if password.lower() in common:
        return False, "Password is too common"
    return True, "OK"

def verify_telegram_init_data(init_data: str, bot_token: str) -> tuple[bool, Dict[str, Any], str]:
    """
    Validate Telegram WebApp initData
    Returns (is_valid, user_data, error_message)
    """
    try:
        if not init_data or not bot_token:
            return False, {}, "Missing initData or bot token"
        
        # Parse initData
        params = {}
        for pair in init_data.split("&"):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            from urllib.parse import unquote
            params[k] = unquote(v)
        
        if "hash" not in params:
            return False, {}, "Missing hash"
        
        received_hash = params.pop("hash")
        
        # Check auth_date for replay attack (allow 24h)
        if "auth_date" in params:
            try:
                auth_date = int(params["auth_date"])
                now = int(time.time())
                if now - auth_date > 86400:  # 24 hours
                    return False, {}, "Auth date too old"
            except ValueError:
                return False, {}, "Invalid auth_date"
        
        # Create data_check_string
        data_check_string = "\n".join([f"{k}={params[k]}" for k in sorted(params.keys())])
        
        # Create secret key
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        
        # Calculate hash
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(calculated_hash, received_hash):
            return False, {}, "Invalid hash"
        
        # Parse user data
        user_data = {}
        if "user" in params:
            try:
                user_data = json.loads(params["user"])
            except:
                user_data = {}
        
        return True, user_data, "OK"
    except Exception as e:
        return False, {}, f"Validation error: {str(e)}"

def generate_order_number() -> str:
    import random, string
    prefix = "VYRON"
    rand = ''.join(random.choices(string.digits, k=10))
    timestamp = str(int(time.time()))[-6:]
    return f"{prefix}-{timestamp}{rand[:4]}"

def generate_idempotency_key() -> str:
    return f"{secrets.token_hex(16)}-{int(time.time())}"

def sanitize_filename(filename: str) -> str:
    import re
    # Remove path traversal
    filename = filename.replace("..", "").replace("/", "_").replace("\\", "_")
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    return filename[:255]
