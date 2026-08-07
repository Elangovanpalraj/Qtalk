from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.status.models import Status, StatusView

router = APIRouter(prefix="/status", tags=["Status"])

@router.post("/create")
def create_status(user_id: int, text_content: str = None, media_url: str = None, db: Session = Depends(get_db)):
    status = Status(user_id=user_id, text_content=text_content, media_url=media_url)
    db.add(status)
    db.commit()
    return {"status": "created", "id": status.id}

@router.get("/active")
def get_active_statuses(db: Session = Depends(get_db)):
    # Returns only statuses younger than 24 hours
    now = datetime.utcnow()
    statuses = db.query(Status).filter(Status.expires_at > now).all()
    return statuses

@router.post("/view/{status_id}")
def view_status(status_id: int, viewer_id: int, db: Session = Depends(get_db)):
    view = StatusView(status_id=status_id, viewer_id=viewer_id)
    db.add(view)
    db.commit()
    return {"status": "viewed"}
