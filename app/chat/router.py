from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db, SessionLocal
from app.models import Message
from app.chat.manager import manager

router = APIRouter()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(user_id, websocket)
    db = SessionLocal()
    try:
        while True:
            data = await websocket.receive_json()
            receiver_id = data.get("receiver_id")
            content = data.get("content")
            media_url = data.get("media_url")

            # Store in DB
            new_msg = Message(
                sender_id=user_id,
                receiver_id=receiver_id,
                content=content,
                media_url=media_url
            )
            db.add(new_msg)
            db.commit()
            db.refresh(new_msg)

            payload = {
                "id": new_msg.id,
                "sender_id": user_id,
                "receiver_id": receiver_id,
                "content": content,
                "media_url": media_url,
                "timestamp": new_msg.timestamp.strftime("%H:%M")
            }

            # Echo to sender and transmit to receiver
            await websocket.send_json(payload)
            await manager.send_direct_message(receiver_id, payload)
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    finally:
        db.close()

@router.get("/history/{user_id}/{peer_id}")
def get_chat_history(user_id: int, peer_id: int, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == peer_id)) |
        ((Message.sender_id == peer_id) & (Message.receiver_id == user_id))
    ).order_by(Message.timestamp.asc()).all()
    
    return [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "receiver_id": m.receiver_id,
            "content": m.content,
            "media_url": m.media_url,
            "timestamp": m.timestamp.strftime("%H:%M")
        } for m in messages
    ]
