from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class Status(Base):
    __tablename__ = "statuses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Status Content (Image, Video, or Text)
    status_type = Column(String, default="image")       # image, video, text
    media_url = Column(String, nullable=True)           # படம் / வீடியோ URL
    text_content = Column(Text, nullable=True)          # Text Status அல்லது Caption
    background_color = Column(String, nullable=True)     # Text Status-ற்கான பின்னணி நிறம் (e.g., #FF5733)

    # 24h Expiry Management
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)       # 24 மணி நேரத்தில் காலாவதியாகும் நேரம்

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    views = relationship("StatusView", back_populates="status", cascade="all, delete-orphan")


class StatusView(Base):
    __tablename__ = "status_views"

    id = Column(Integer, primary_key=True, index=True)
    status_id = Column(Integer, ForeignKey("statuses.id", ondelete="CASCADE"), nullable=False)
    viewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    viewed_at = Column(DateTime, default=default=datetime.utcnow, nullable=False)

    # Relationships
    status = relationship("Status", back_populates="views")
    viewer = relationship("User", foreign_keys=[viewer_id])

    # ஒரே பயனர் ஒரே Status-ஐ பலமுறை பார்த்தாலும் ஒருமுறை மட்டுமே பதிவாவதை உறுதி செய்ய
    __table_args__ = (
        UniqueConstraint("status_id", "viewer_id", name="unique_status_viewer"),
    )
