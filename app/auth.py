import random
import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.config import DEV_OTP, OTP_TTL_SECONDS
from app.database import get_db
from app.models import OTPCode, User
from app.security import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

def normalize_phone(phone: str) -> str:
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 8 or len(digits) > 15:
        raise HTTPException(400, "Invalid phone number")
    # Keep the canonical digits. For Indian 10-digit numbers this intentionally
    # remains 10 digits; +91 input is reduced to the same final 10 digits.
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits

class PhoneIn(BaseModel):
    phone: str = Field(min_length=8, max_length=32)

class VerifyIn(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    otp: str = Field(min_length=4, max_length=10)
    name: str | None = None

@router.post("/send-otp")
def send_otp(data: PhoneIn, db: Session = Depends(get_db)):
    phone = normalize_phone(data.phone)
    # invalidate previous unused OTPs for the same number
    db.query(OTPCode).filter(OTPCode.phone == phone, OTPCode.used == False).update({OTPCode.used: True})
    code = f"{random.randint(0, 999999):06d}"
    db.add(OTPCode(phone=phone, code=code, expires_at=datetime.utcnow()+timedelta(seconds=OTP_TTL_SECONDS)))
    db.commit()
    response = {"success": True, "message": "OTP generated."}
    if DEV_OTP:
        response["dev_otp"] = code
    return response

@router.post("/verify-otp")
def verify_otp(data: VerifyIn, response: Response, request: Request, db: Session = Depends(get_db)):
    phone = normalize_phone(data.phone)
    otp = db.query(OTPCode).filter(OTPCode.phone == phone, OTPCode.code == data.otp, OTPCode.used == False).order_by(OTPCode.id.desc()).first()
    if not otp or otp.expires_at < datetime.utcnow():
        raise HTTPException(401, "Invalid or expired OTP")
    otp.used = True
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(phone=phone, name=(data.name or "User").strip()[:120])
        db.add(user)
    elif data.name and data.name.strip():
        user.name = data.name.strip()[:120]
    user.last_seen = datetime.utcnow()
    db.commit(); db.refresh(user)
    token = create_token(user.id)
    # Browser-persistent session. JS localStorage remains the primary client
    # cache, while this cookie lets the app recover after a storage reset.
    response.set_cookie(
        "qtalk_session", token, max_age=30*24*60*60, httponly=True,
        secure=request.url.scheme == "https", samesite="lax", path="/"
    )
    return {"success": True, "token": token, "user": {"id": user.id, "phone": user.phone, "name": user.name, "about": user.about, "avatar_url": user.avatar_url}}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("qtalk_session", path="/")
    return {"success": True}
