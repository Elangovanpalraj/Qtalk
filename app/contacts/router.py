from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.contacts.models import User, Contact

router = APIRouter(prefix="/contacts", tags=["Contacts & Users"])


# ------------------------------------------------------------------
# 🟢 Pydantic Request Models
# ------------------------------------------------------------------
class RegisterRequest(BaseModel):
    phone_number: str
    username: Optional[str] = "Qtalk User"
    bio: Optional[str] = "Hey there! I am using Qtalk."


class AddContactRequest(BaseModel):
    user_phone: str
    contact_phone: str


# ------------------------------------------------------------------
# 🟢 1. Register / Sync User API
# ------------------------------------------------------------------
@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone_number == data.phone_number).first()
    if not user:
        username = data.username if data.username else f"User {data.phone_number[-4:]}"
        user = User(
            phone_number=data.phone_number,
            username=username,
            bio=data.bio
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    return {
        "success": True, 
        "message": "User registered successfully", 
        "user_id": user.id,
        "phone_number": user.phone_number,
        "username": user.username
    }


# ------------------------------------------------------------------
# 🟢 2. Add Contact API
# ------------------------------------------------------------------
@router.post("/add")
def add_contact(data: AddContactRequest, db: Session = Depends(get_db)):
    current_user = db.query(User).filter(User.phone_number == data.user_phone).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="Current user not found in Qtalk!")

    target_user = db.query(User).filter(User.phone_number == data.contact_phone).first()
    if not target_user:
        return {"success": False, "message": "User not registered on Qtalk!"}

    if current_user.id == target_user.id:
        return {"success": False, "message": "You cannot add yourself as a contact!"}

    existing_contact = db.query(Contact).filter(
        Contact.user_id == current_user.id,
        Contact.contact_user_id == target_user.id
    ).first()

    if not existing_contact:
        new_contact = Contact(
            user_id=current_user.id,
            contact_user_id=target_user.id
        )
        db.add(new_contact)
        db.commit()

    return {"success": True, "message": "Contact added successfully!"}


# ------------------------------------------------------------------
# 🟢 3. Get Contacts List API
# ------------------------------------------------------------------
@router.get("/{user_phone}")
def get_contacts(user_phone: str, db: Session = Depends(get_db)):
    current_user = db.query(User).filter(User.phone_number == user_phone).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")

    contacts = db.query(Contact).filter(Contact.user_id == current_user.id).all()
    
    result = []
    for c in contacts:
        contact_user = db.query(User).filter(User.id == c.contact_user_id).first()
        if contact_user:
            result.append({
                "id": contact_user.id,
                "phone_number": contact_user.phone_number,
                "username": contact_user.username,
                "profile_pic": contact_user.profile_pic,
                "bio": contact_user.bio,
                "is_online": contact_user.is_online,
                "is_blocked": c.is_blocked
            })
            
    return {"success": True, "contacts": result}
