from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from typing import List
from datetime import datetime

from .schemas import (
    InitiateCallRequest,
    UpdateCallStatusRequest,
    CallLogResponse
)
from .utils import call_manager

router = APIRouter(
    prefix="/calls",
    tags=["Calls & WebRTC Signaling"]
)

# Mock DB for storing call history
MOCK_CALL_LOGS = []


@router.post("/initiate")
async def initiate_call(payload: InitiateCallRequest, caller_id: int = 1):
    """
    Initiate an Audio or Video call with another user.
    """
    call_id = len(MOCK_CALL_LOGS) + 1
    call_entry = {
        "id": call_id,
        "caller_id": caller_id,
        "receiver_id": payload.receiver_id,
        "call_type": payload.call_type,
        "status": "ringing",
        "duration_seconds": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    MOCK_CALL_LOGS.append(call_entry)

    # Notify target user if connected to WebSocket
    signaled = await call_manager.send_signal(payload.receiver_id, {
        "event": "incoming_call",
        "call_id": call_id,
        "caller_id": caller_id,
        "call_type": payload.call_type
    })

    return {
        "success": True,
        "call_id": call_id,
        "receiver_online": signaled,
        "message": "Call initiated successfully"
    }


@router.post("/update-status")
async def update_call_status(payload: UpdateCallStatusRequest):
    """
    Update call status (answered, rejected, ended).
    """
    for call in MOCK_CALL_LOGS:
        if call["id"] == payload.call_id:
            call["status"] = payload.status
            call["duration_seconds"] = payload.duration_seconds
            return {"success": True, "message": f"Call status updated to '{payload.status}'"}
    
    raise HTTPException(status_code=404, detail="Call session not found")


@router.get("/history", response_model=List[dict])
async def get_call_history(user_id: int = 1):
    """
    Get call log history (incoming, outgoing, missed) for a user.
    """
    user_calls = [
        call for call in MOCK_CALL_LOGS 
        if call["caller_id"] == user_id or call["receiver_id"] == user_id
    ]
    return user_calls


@router.websocket("/ws/{user_id}")
async def call_websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    WebSocket Endpoint for WebRTC Signaling (SDP Offer, Answer & ICE Candidates).
    """
    await call_manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            target_id = data.get("target_user_id")
            
            if target_id:
                await call_manager.send_signal(target_id, {
                    "sender_id": user_id,
                    "signal_data": data
                })
    except WebSocketDisconnect:
        call_manager.disconnect(user_id)
