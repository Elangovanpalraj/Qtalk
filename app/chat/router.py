import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.chat.models import Message
from app.chat.manager import manager

router = APIRouter(prefix="", tags=["Chat"])

@router.get("/messages/{user1}/{user2}")
def get_chat_history(user1: str, user2: str, db: Session = Depends(get_db)):
    msgs = db.query(Message).filter(
        ((Message.sender == user1) & (Message.receiver == user2)) |
        ((Message.sender == user2) & (Message.receiver == user1))
    ).order_by(Message.id.asc()).all()
    
    return [
        {
            "id": m.id,
            "sender": m.sender,
            "receiver": m.receiver,
            "message": m.message,
            "file_url": m.file_url,
            "timestamp": m.timestamp,
            "is_read": m.is_read
        } for m in msgs
    ]

@router.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str, db: Session = Depends(get_db)):
    await manager.connect(username, websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            msg_type = data.get("type")

            if msg_type == "message":
                receiver = data.get("receiver")
                text = data.get("message", "")
                file_url = data.get("file_url", "")
                
                msg_obj = Message(
                    sender=username,
                    receiver=receiver,
                    message=text,
                    file_url=file_url
                )
                db.add(msg_obj)
                db.commit()
                db.refresh(msg_obj)

                payload = json.dumps({
                    "type": "message",
                    "id": msg_obj.id,
                    "sender": username,
                    "receiver": receiver,
                    "message": text,
                    "file_url": file_url,
                    "timestamp": msg_obj.timestamp
                })

                await manager.send_personal_message(payload, receiver)
                await manager.send_personal_message(payload, username)

    except WebSocketDisconnect:
        manager.disconnect(username)
        await manager.broadcast_status()

@router.delete("/message/{msg_id}")
def delete_message(msg_id: int, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == msg_id).first()
    if msg:
        db.delete(msg)
        db.commit()
        return {"status": "success", "id": msg_id}
    return {"status": "not_found"}