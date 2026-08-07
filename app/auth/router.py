import random
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict

from .schemas import (
    SendOTPRequest, 
    VerifyOTPRequest, 
    GenericResponse, 
    TokenResponse, 
    UserProfileResponse, 
    UpdateProfileRequest
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication & User Profile"]
)

# In-memory database mock (Connect your SQLAlchemy Session in production)
MOCK_OTP_DB: Dict[str, str] = {}
MOCK_USERS_DB: Dict[str, dict] = {}


def generate_mock_jwt(phone: str, user_id: int) -> str:
    """Generate a dummy JWT token string for authentication."""
    return f"qtalk_jwt_token_{user_id}_{phone.replace('+', '')}"


@router.post("/send-otp", response_model=GenericResponse)
async def send_otp(payload: SendOTPRequest):
    """
    Generate and send a 6-digit OTP to the user's phone number.
    """
    phone = payload.phone.strip()
    
    if len(phone) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid phone number format"
        )

    # Generate fixed/random 6-digit OTP (Static '123456' for easy testing)
    otp_code = "123456"  # Or use: str(random.randint(100000, 999999))
    MOCK_OTP_DB[phone] = otp_code

    # Here you can integrate SMS service like Twilio / Fast2SMS
    return GenericResponse(
        success=True, 
        message=f"OTP sent successfully to {phone} (Test OTP: {otp_code})"
    )


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(payload: VerifyOTPRequest):
    """
    Verify the 6-digit OTP and return an Access Token.
    """
    phone = payload.phone.strip()
    user_otp = payload.otp.strip()

    stored_otp = MOCK_OTP_DB.get(phone)
    
    if not stored_otp or stored_otp != user_otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or expired OTP"
        )

    # Create or fetch user
    if phone not in MOCK_USERS_DB:
        user_id = len(MOCK_USERS_DB) + 1
        MOCK_USERS_DB[phone] = {
            "id": user_id,
            "phone": phone,
            "name": "User " + str(user_id),
            "about": "Hey there! I am using Qtalk.",
            "avatar_url": f"https://ui-avatars.com/api/?name=User+{user_id}",
            "is_active": True,
            "created_at": "2026-08-07T10:00:00"
        }

    user = MOCK_USERS_DB[phone]
    access_token = generate_mock_jwt(phone, user["id"])
    
    # Clear OTP after successful login
    del MOCK_OTP_DB[phone]

    return TokenResponse(
        success=True,
        access_token=access_token,
        token_type="bearer",
        user_id=user["id"]
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(phone: str):
    """
    Fetch the currently logged in user profile details.
    """
    if phone not in MOCK_USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found"
        )
    return MOCK_USERS_DB[phone]


@router.put("/me", response_model=UserProfileResponse)
async def update_profile(phone: str, payload: UpdateProfileRequest):
    """
    Update logged-in user profile details (Name, About, Avatar).
    """
    if phone not in MOCK_USERS_DB:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found"
        )

    user = MOCK_USERS_DB[phone]
    if payload.name:
        user["name"] = payload.name
    if payload.about:
        user["about"] = payload.about
    if payload.avatar_url:
        user["avatar_url"] = payload.avatar_url

    return user
