from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class Status(Base):
    __tablename__ = "statuses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Status Content (Image, Video, or Text)
    media_url = Column(String, nullable=True)       # Upload செய்யப்பட்ட படம்/வீடியோ URL
    caption = Column(Text, nullable=True)           # Status கேப்ஷன் (Text)
    status_type = Column(String, default="image")   # image, video, text
    background_color = Column(String, nullable=True) # Text Status-க்கான கலர் (e.g., #FF5733)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    views = relationship("StatusView", back_populates="status", cascade="all, delete-orphan")


class StatusView(Base):
    __tablename__ = "status_views"

    id = Column(Integer, primary_key=True, index=True)
    status_id = Column(Integer, ForeignKey("statuses.id"), nullable=False)
    viewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    viewed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    status = relationship("Status", back_populates="views")
    viewer = relationship("User", foreign_keys=[viewer_id])
