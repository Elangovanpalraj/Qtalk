from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Table, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base

group_members = Table(
    "group_members", Base.metadata,
    Column("group_id", ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    phone = Column(String(32), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False, default="User")
    about = Column(String(255), nullable=False, default="Hey there! I am using Qtalk.")
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_online = Column(Boolean, default=False)

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    contact_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    nickname = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("owner_id", "contact_id", name="uq_contact_owner_target"),)

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True)
    kind = Column(String(20), nullable=False, default="direct")
    title = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    members = relationship("User", secondary=group_members, lazy="joined")

class DirectChatKey(Base):
    __tablename__ = "direct_chat_keys"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), unique=True, nullable=False)
    chat_key = Column(String(50), unique=True, nullable=False, index=True)
    __table_args__ = (UniqueConstraint("chat_id", name="uq_direct_chat_key_chat"),)

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), index=True, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    text = Column(Text, nullable=True)
    media_url = Column(String(500), nullable=True)
    media_type = Column(String(30), nullable=True)
    file_name = Column(String(255), nullable=True)
    reply_to_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    delivered_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    __table_args__ = (Index("ix_messages_chat_created", "chat_id", "created_at", "id"),)

class MessageClientKey(Base):
    __tablename__ = "message_client_keys"
    id = Column(Integer, primary_key=True)
    client_id = Column(String(80), unique=True, nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class MessageDelivery(Base):
    __tablename__ = "message_deliveries"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    delivered_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_message_delivery"),)

class MessageReaction(Base):
    __tablename__ = "message_reactions"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    emoji = Column(String(20), nullable=False)
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_message_reaction_user"),)

class ReadReceipt(Base):
    __tablename__ = "read_receipts"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    read_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_read_receipt"),)

class MessageEdit(Base):
    __tablename__ = "message_edits"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    editor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    old_text = Column(Text, nullable=True)
    edited_at = Column(DateTime, default=datetime.utcnow)

class MessageStar(Base):
    __tablename__ = "message_stars"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_message_star"),)

class MessagePin(Base):
    __tablename__ = "message_pins"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True)
    pinned_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pinned_at = Column(DateTime, default=datetime.utcnow)

class Status(Base):
    __tablename__ = "statuses"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    text = Column(Text, nullable=True)
    media_url = Column(String(500), nullable=True)
    background = Column(String(30), default="#075E54")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False)

class StatusView(Base):
    __tablename__ = "status_views"
    id = Column(Integer, primary_key=True)
    status_id = Column(Integer, ForeignKey("statuses.id", ondelete="CASCADE"), nullable=False, index=True)
    viewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("status_id", "viewer_id", name="uq_status_view"),)

class OTPCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True)
    phone = Column(String(32), index=True, nullable=False)
    code = Column(String(10), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

class ChatUserSetting(Base):
    __tablename__ = "chat_user_settings"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    muted = Column(Boolean, default=False)
    archived = Column(Boolean, default=False)
    cleared_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_user_setting"),)

class Block(Base):
    __tablename__ = "blocks"
    id = Column(Integer, primary_key=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block"),)

class GroupMemberMeta(Base):
    __tablename__ = "group_member_meta"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    is_admin = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_group_member_meta"),)
