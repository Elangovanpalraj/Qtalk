from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    username: str
    phone_number: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    phone_number: Optional[str]

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    receiver_id: int
    content: str

class MessageResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    is_read: bool
    timestamp: datetime

    class Config:
        from_attributes = True
