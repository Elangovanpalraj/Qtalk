from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Status

router = APIRouter()

class StatusCreate(BaseModel):
    user_id: int
    content: str

@router.post("/")
def create_status(status_in: StatusCreate, db: Session = Depends(get_db)):
    new_status = Status(user_id=status_in.user_id, content=status_in.content)
    db.add(new_status)
    db.commit()
    db.refresh(new_status)
    return {"message": "Status updated successfully"}

@router.get("/")
def get_all_statuses(db: Session = Depends(get_db)):
    statuses = db.query(Status).order_by(Status.created_at.desc()).all()
    return [{"id": s.id, "user_id": s.user_id, "username": s.user.username, "content": s.content} for s in statuses]
