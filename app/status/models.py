from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime, timedelta
from app.database import Base

class Status(Base):
    __tablename__ = "statuses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    media_url = Column(String, nullable=True)
    text_content = Column(Text, nullable=True)
    background_color = Column(String, default="#000000")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=24))

class StatusView(Base):
    __tablename__ = "status_views"

    id = Column(Integer, primary_key=True, index=True)
    status_id = Column(Integer, ForeignKey("statuses.id"))
    viewer_id = Column(Integer, ForeignKey("users.id"))
    viewed_at = Column(DateTime, default=datetime.utcnow)
