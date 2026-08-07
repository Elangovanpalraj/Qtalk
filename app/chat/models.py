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

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="group_default.png")
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    is_admin = Column(Boolean, default=False)

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True) # None for group chats
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    
    # Message Types: text, image, video, voice, document, location, contact
    msg_type = Column(String, default="text") 
    content = Column(Text, nullable=True)
    media_url = Column(String, nullable=True)
    
    # Reply & Forwarding
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    is_forwarded = Column(Boolean, default=False)
    
    # Message Status: sent, delivered, read
    status = Column(String, default="sent") 
    
    # Edit / Delete Flags
    is_edited = Column(Boolean, default=False)
    is_deleted_everyone = Column(Boolean, default=False)
    deleted_for_users = Column(Text, default="") # Comma-separated user IDs
    
    created_at = Column(DateTime, default=datetime.utcnow)

class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    emoji = Column(String(10), nullable=False)
