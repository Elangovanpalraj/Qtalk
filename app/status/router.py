from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.status.models import Status, StatusView

router = APIRouter(prefix="/status", tags=["Status / Stories (24 Hours)"])


# ------------------------------------------------------------------
# 🟢 1. PYDANTIC SCHEMAS (Request Body Validation)
# ------------------------------------------------------------------
class StatusCreateSchema(BaseModel):
    user_id: int
    text_content: Optional[str] = None
    media_url: Optional[str] = None


class StatusViewSchema(BaseModel):
    viewer_id: int


# ------------------------------------------------------------------
# 🟢 2. STATUS CREATION ENDPOINT
# ------------------------------------------------------------------
@router.post("/create")
def create_status(data: StatusCreateSchema, db: Session = Depends(get_db)):
    """
    புதிய Status/Story உருவாக்க பயன்படும் API. 
    இது உருவாக்கப்பட்ட நேரத்தில் இருந்து 24 மணி நேரம் கழித்து தானாகக் காலாவதியாகும் (Expires).
    """
    if not data.text_content and not data.media_url:
        raise HTTPException(
            status_code=400, 
            detail="Either text_content or media_url must be provided."
        )

    now = datetime.utcnow()
    expires_at = now + timedelta(hours=24)

    new_status = Status(
        user_id=data.user_id,
        text_content=data.text_content,
        media_url=data.media_url,
        created_at=now,
        expires_at=expires_at
    )
    db.add(new_status)
    db.commit()
    db.refresh(new_status)

    return {
        "success": True,
        "message": "Status created successfully",
        "status_id": new_status.id,
        "expires_at": new_status.expires_at.isoformat()
    }


# ------------------------------------------------------------------
# 🟢 3. FETCH ACTIVE STATUSES (Under 24 Hours)
# ------------------------------------------------------------------
@router.get("/active")
def get_active_statuses(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """
    தற்போது நேரலையில் (24 மணி நேரத்திற்குள்) உள்ள அனைத்து Status-களையும் பெற உதவும் API.
    புதிதாக பதிவிடப்பட்ட Status முதன்மையாக வரும் (Newest first).
    """
    now = datetime.utcnow()
    query = db.query(Status).filter(Status.expires_at > now)

    # குறிப்பிட்ட பயனரின் Active Statuses மட்டும் வேண்டுமென்றால் filter செய்யலாம்
    if user_id:
        query = query.filter(Status.user_id == user_id)

    statuses = query.order_by(Status.created_at.desc()).all()
    return {"success": True, "count": len(statuses), "statuses": statuses}


# ------------------------------------------------------------------
# 🟢 4. MARK STATUS AS VIEWED
# ------------------------------------------------------------------
@router.post("/view/{status_id}")
def view_status(status_id: int, data: StatusViewSchema, db: Session = Depends(get_db)):
    """
    ஒருவரது Status-ஐ பார்க்கும் போது, Viewer விபரங்களைப் பதிவு செய்யும் API.
    ஏற்கனவே பார்த்திருந்தால் மீண்டும் பதிவு செய்யாது (Duplicate entry தவிர்க்கப்படும்).
    """
    status_item = db.query(Status).filter(Status.id == status_id).first()
    if not status_item:
        raise HTTPException(status_code=404, detail="Status not found")

    # Status 24 மணி நேரத்தைத் தாண்டிவிட்டதா என சரிபார்க்கவும்
    if datetime.utcnow() > status_item.expires_at:
        raise HTTPException(status_code=400, detail="This status has expired")

    # Duplicate View செக் செய்ய (ஏற்கனவே பார்த்துவிட்டாரா?)
    existing_view = db.query(StatusView).filter(
        StatusView.status_id == status_id,
        StatusView.viewer_id == data.viewer_id
    ).first()

    if not existing_view:
        new_view = StatusView(status_id=status_id, viewer_id=data.viewer_id)
        db.add(new_view)
        db.commit()

    return {"success": True, "status_id": status_id, "viewed_by": data.viewer_id}


# ------------------------------------------------------------------
# 🟢 5. GET VIEWER LIST FOR A STATUS
# ------------------------------------------------------------------
@router.get("/viewers/{status_id}")
def get_status_viewers(status_id: int, user_id: int, db: Session = Depends(get_db)):
    """
    Status போட்டவர், தனது Status-ஐ யார் யாரெல்லாம் பார்த்தார்கள் என்று பார்க்கும் API.
    """
    status_item = db.query(Status).filter(Status.id == status_id).first()
    if not status_item:
        raise HTTPException(status_code=404, detail="Status not found")

    # போட்டவர் மட்டுமே பார்க்க அனுமதி
    if status_item.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Permission denied to view this viewer list"
        )

    views = db.query(StatusView).filter(StatusView.status_id == status_id).all()
    viewer_ids = [v.viewer_id for v in views]

    return {
        "success": True,
        "status_id": status_id,
        "total_views": len(viewer_ids),
        "viewers": viewer_ids
    }


# ------------------------------------------------------------------
# 🟢 6. DELETE STATUS
# ------------------------------------------------------------------
@router.delete("/delete/{status_id}")
def delete_status(status_id: int, user_id: int, db: Session = Depends(get_db)):
    """
    தனது Status-ஐ 24 மணி நேரத்திற்கு முன்பே கைமுறையாக Delete செய்யும் API.
    """
    status_item = db.query(Status).filter(Status.id == status_id, Status.user_id == user_id).first()
    if not status_item:
        raise HTTPException(status_code=404, detail="Status not found or permission denied")

    # Status-க்கு தொடர்புடைய Views records-ஐ முதலில் நீக்குவோம்
    db.query(StatusView).filter(StatusView.status_id == status_id).delete()
    
    db.delete(status_item)
    db.commit()

    return {"success": True, "message": "Status deleted successfully", "status_id": status_id}
