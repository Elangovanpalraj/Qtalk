from sqlalchemy import Column, Integer, String, Text, Boolean
from datetime import datetime
from app.database import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String(100), nullable=False)
    receiver = Column(String(100), nullable=False)
    message = Column(Text, nullable=True)
    file_url = Column(Text, nullable=True)
    timestamp = Column(String(50), default=lambda: datetime.now().strftime("%I:%M %p"))
    is_read = Column(Boolean, default=False)