from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    password_confirm: str
    display_name: Optional[str] = Field(None, max_length=100)
    language: str = Field(default="uz")

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

class UserLoginRequest(BaseModel):
    email_or_username: str
    password: str
    remember_me: bool = False

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool
    is_admin: bool
    language: str
    theme: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class SessionResponse(BaseModel):
    user: UserResponse
    session_token: str
    expires_at: datetime

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v

class TelegramAuthRequest(BaseModel):
    initData: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v
