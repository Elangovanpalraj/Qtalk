from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Integer
from pydantic import BaseModel
from app.database import get_db, Base, engine

# 🟢 1. Database Tables for Users and Contacts
class UserDB(Base):
    __tablename__ = "qtalk_users"
    phone = Column(String, primary_primary=True if False else False, primary_key=True, index=True)
    name = Column(String, default="Qtalk User")

class ContactDB(Base):
    __tablename__ = "qtalk_contacts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_phone = Column(String, index=True)
    contact_phone = Column(String, index=True)

# Create Tables automatically
Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="", tags=["Contacts"])

# Request Body Models
class RegisterRequest(BaseModel):
    phone: str
    name: str = "Qtalk User"

class AddContactRequest(BaseModel):
    user_phone: str
    contact_phone: str


# 🟢 2. Register API (பயனர் லாகின் பண்ணும்போது DB-ல் சேமிக்கும்)
@router.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.phone == data.phone).first()
    if not user:
        new_user = UserDB(phone=data.phone, name=data.name or f"User {data.phone[-4:]}")
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    return {"success": True, "message": "User registered successfully"}


# 🟢 3. Add Contact API (புது Contact ஆட் செய்யும்போது DB-ல் செக் பண்ணும்)
@router.post("/contacts/add")
def add_contact(data: AddContactRequest, db: Session = Depends(get_db)):
    # 1. Target User Qtalk-ல் இருக்கிறாரா என பார்ப்பது
    target = db.query(UserDB).filter(UserDB.phone == data.contact_phone).first()
    if not target:
        return {"success": False, "message": "User not registered on Qtalk!"}

    # 2. ஏற்கனவே Add பண்ணியிருக்கிறாரா என பார்ப்பது
    existing = db.query(ContactDB).filter(
        ContactDB.user_phone == data.user_phone,
        ContactDB.contact_phone == data.contact_phone
    ).first()

    if not existing:
        new_contact = ContactDB(user_phone=data.user_phone, contact_phone=data.contact_phone)
        db.add(new_contact)
        db.commit()

    return {"success": True, "message": "Contact added successfully!"}


# 🟢 4. Get Contacts API (பயனரின் Contact List-ஐ எடுப்பது)
@router.get("/contacts/{user_phone}")
def get_contacts(user_phone: str, db: Session = Depends(get_db)):
    contacts = db.query(ContactDB).filter(ContactDB.user_phone == user_phone).all()
    result = []
    for c in contacts:
        u = db.query(UserDB).filter(UserDB.phone == c.contact_phone).first()
        if u:
            result.append({"phone": u.phone, "name": u.name})
    return result
