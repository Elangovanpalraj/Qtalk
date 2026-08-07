from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class InitiateCallRequest(BaseModel):
    receiver_id: int
    call_type: str = "audio"  # "audio" or "video"


class UpdateCallStatusRequest(BaseModel):
    call_id: int
    status: str              # "answered", "rejected", "ended"
    duration_seconds: Optional[int] = 0


class CallLogResponse(BaseModel):
    id: int
    caller_id: int
    receiver_id: int
    call_type: str
    status: str
    duration_seconds: int
    created_at: datetime

    class Config:
        from_attributes = True


class WebRTCSignalingSchema(BaseModel):
    target_user_id: int
    type: str                # "offer", "answer", "ice-candidate", "end-call"
    sdp: Optional[str] = None
    candidate: Optional[dict] = None
