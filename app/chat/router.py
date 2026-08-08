import json
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from sqlalchemy import or_, and_

from app.database import get_db
from app.chat.models import Message, MessageReaction, Group, GroupMember
from app.chat.manager import manager

# Prefix-ah remove panniyullathu, enenal frontend direct-ah /ws matrum /messages call pannugirathu.
router = APIRouter(tags=["Chat Core & Real-time"])


# ------------------------------------------------------------------
# 🟢 1. PYDANTIC SCHEMAS (REST Request Models)
# ------------------------------------------------------------------
class GroupCreateSchema(BaseModel):
    name: str
    admin_id: int
    member_ids: List[int]


class EditMessageSchema(BaseModel):
    user_id: int
    new_content: str


class ReactionSchema(BaseModel):
    user_id: int
    emoji: str


# ------------------------------------------------------------------
# 🟢 2. FETCH CHAT HISTORY (Fixes 404 Messages API Error)
# ------------------------------------------------------------------
@router.get("/messages/{user_id}/{other_id}")
def get_chat_history(user_id: int, other_id: int, db: Session = Depends(get_db)):
    """
    iruvarukku idaiyeana chat history-ai database-il irunthu eduthu tharum API.
    """
    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        )
    ).order_by(Message.created_at.asc()).all()
    
    return messages


# ------------------------------------------------------------------
# 🟢 3. WEBSOCKET REAL-TIME ENDPOINT
# ------------------------------------------------------------------
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):
    """
    Real-time WebSocket endpoint: Handles direct messages, group chats,
    typing indicators, read receipts, reactions, and WebRTC call signaling.
    """
    await manager.connect(user_id, websocket)

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            event = data.get("event") or data.get("type")

            # ------------------------------------------------------
            # A. SEND MESSAGE (Direct or Group)
            # ------------------------------------------------------
            if event in ["send_message", "message"]:
                receiver_id = data.get("receiver_id")
                group_id = data.get("group_id")

                new_msg = Message(
                    sender_id=user_id,
                    receiver_id=receiver_id,
                    group_id=group_id,
                    msg_type=data.get("msg_type", "text"),
                    content=data.get("content"),
                    media_url=data.get("media_url") or data.get("file_url"),
                    reply_to_id=data.get("reply_to_id"),
                    status="delivered" if (receiver_id and manager.is_user_online(receiver_id)) else "sent"
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                payload = {
                    "event": "new_message",
                    "id": new_msg.id,
                    "sender_id": user_id,
                    "receiver_id": receiver_id,
                    "group_id": group_id,
                    "msg_type": new_msg.msg_type,
                    "content": new_msg.content,
                    "media_url": new_msg.media_url,
                    "status": new_msg.status,
                    "reply_to_id": new_msg.reply_to_id,
                    "created_at": new_msg.created_at.isoformat()
                }

                if group_id:
                    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
                    member_ids = [m.user_id for m in members]
                    await manager.broadcast_to_users(payload, member_ids, exclude_sender_id=user_id)
                elif receiver_id:
                    await manager.send_personal_message(payload, receiver_id)
                    await manager.send_personal_message(payload, user_id)

            # ------------------------------------------------------
            # B. TYPING INDICATOR
            # ------------------------------------------------------
            elif event == "typing":
                target_id = data.get("receiver_id")
                is_typing = data.get("is_typing", True)
                if target_id:
                    await manager.send_typing_indicator(user_id, target_id, is_typing)

            # ------------------------------------------------------
            # C. MARK AS READ (Blue Ticks)
            # ------------------------------------------------------
            elif event == "mark_read":
                msg_ids = data.get("message_ids", [])
                if msg_ids:
                    db.query(Message).filter(Message.id.in_(msg_ids)).update(
                        {"status": "read"}, synchronize_session=False
                    )
                    db.commit()

                    sender_id = data.get("sender_id")
                    if sender_id:
                        await manager.send_personal_message(
                            {"event": "read_ack", "message_ids": msg_ids, "read_by": user_id},
                            sender_id
                        )

            # ------------------------------------------------------
            # D. EMOJI REACTIONS
            # ------------------------------------------------------
            elif event == "reaction":
                msg_id = data.get("message_id")
                emoji = data.get("emoji")

                if msg_id and emoji:
                    react = MessageReaction(message_id=msg_id, user_id=user_id, emoji=emoji)
                    db.add(react)
                    db.commit()

                    react_payload = {
                        "event": "message_reaction",
                        "message_id": msg_id,
                        "user_id": user_id,
                        "emoji": emoji
                    }

                    target_id = data.get("receiver_id")
                    if target_id:
                        await manager.send_personal_message(react_payload, target_id)

            # ------------------------------------------------------
            # E. WEBRTC CALL SIGNALING (Voice & Video Calls)
            # ------------------------------------------------------
            elif event in ["call_offer", "call_answer", "ice_candidate", "end_call"]:
                target_id = data.get("target_id")
                if target_id:
                    data["sender_id"] = user_id
                    await manager.send_personal_message(data, target_id)

    except WebSocketDisconnect:
        manager.disconnect(user_id)


# ------------------------------------------------------------------
# 🟢 4. GROUP MANAGEMENT ENDPOINTS
# ------------------------------------------------------------------
@router.post("/group/create", tags=["Groups"])
def create_group(data: GroupCreateSchema, db: Session = Depends(get_db)):
    if len(data.member_ids) > 1024:
        raise HTTPException(status_code=400, detail="Group capacity exceeded (Max 1024 members)")

    new_group = Group(name=data.name, created_by=data.admin_id)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    all_members = list(set(data.member_ids + [data.admin_id]))
    for m_id in all_members:
        is_admin = (m_id == data.admin_id)
        db.add(GroupMember(group_id=new_group.id, user_id=m_id, is_admin=is_admin))
    
    db.commit()
    return {"success": True, "group_id": new_group.id, "message": f"Group '{data.name}' created successfully"}


# ------------------------------------------------------------------
# 🟢 5. MESSAGE ACTIONS (Edit, Delete for Everyone, Delete for Me)
# ------------------------------------------------------------------
@router.put("/message/edit/{message_id}", tags=["Chat Actions"])
def edit_message(message_id: int, data: EditMessageSchema, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id, Message.sender_id == data.user_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or permission denied")

    if datetime.utcnow() - msg.created_at > timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="Edit window expired (15 mins limit)")

    msg.content = data.new_content
    msg.is_edited = True
    db.commit()
    return {"success": True, "status": "edited", "message_id": message_id, "new_content": data.new_content}


@router.delete("/message/delete_everyone/{message_id}", tags=["Chat Actions"])
def delete_message_everyone(message_id: int, user_id: int, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id, Message.sender_id == user_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found or permission denied")

    msg.is_deleted_everyone = True
    msg.content = "This message was deleted"
    msg.media_url = None
    db.commit()
    return {"success": True, "status": "deleted_everyone", "message_id": message_id}


@router.post("/message/delete_for_me/{message_id}", tags=["Chat Actions"])
def delete_message_for_me(message_id: int, user_id: int, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    deleted_users = [u.strip() for u in (msg.deleted_for_users or "").split(",") if u.strip()]
    if str(user_id) not in deleted_users:
        deleted_users.append(str(user_id))
        msg.deleted_for_users = ",".join(deleted_users)
        db.commit()

    return {"success": True, "status": "deleted_for_me", "message_id": message_id}
