from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SendOTPRequest(BaseModel):
    phone: str = Field(..., example="+919876543210")


class VerifyOTPRequest(BaseModel):
    phone: str = Field(..., example="+919876543210")
    otp: str = Field(..., min_length=6, max_length=6, example="123456")


class GenericResponse(BaseModel):
    success: bool
    message: str


class TokenResponse(BaseModel):
    success: bool
    access_token: str
    token_type: str = "bearer"
    user_id: int


class UserProfileResponse(BaseModel):
    id: int
    phone: str
    name: str
    about: str
    avatar_url: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    about: Optional[str] = None
    avatar_url: Optional[str] = None
