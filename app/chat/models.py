from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    icon = Column(String, default="group_default.png")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_admin = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    group = relationship("Group", back_populates="members")
    user = relationship("User")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # None for group chats
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)     # None for direct chats
    
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
    deleted_for_users = Column(Text, default="")  # Comma-separated user IDs (e.g., "1,4,7")
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    group = relationship("Group", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id], backref="replies")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    message = relationship("Message", back_populates="reactions")
    user = relationship("User")
