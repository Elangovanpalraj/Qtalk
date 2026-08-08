from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

router = APIRouter()

@router.get("/")
def get_contacts(current_user_id: int, db: Session = Depends(get_db)):
    users = db.query(User).filter(User.id != current_user_id).all()
    return [{"id": u.id, "username": u.username, "profile_pic": u.profile_pic} for u in users]
