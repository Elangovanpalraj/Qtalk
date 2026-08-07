from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SendMessageSchema(BaseModel):
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    content: Optional[str] = None
    msg_type: str = "text"
    media_url: Optional[str] = None
    reply_to_id: Optional[int] = None
    is_forwarded: bool = False


class MessageResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: Optional[int] = None
    group_id: Optional[int] = None
    content: Optional[str] = None
    msg_type: str
    media_url: Optional[str] = None
    reply_to_id: Optional[int] = None
    is_forwarded: bool
    status: str
    is_edited: bool
    is_deleted_everyone: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CreateGroupSchema(BaseModel):
    name: str
    icon: Optional[str] = "group_default.png"
    member_ids: List[int] = []


class GroupResponse(BaseModel):
    id: int
    name: str
    icon: str
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class AddReactionSchema(BaseModel):
    message_id: int
    emoji: str
