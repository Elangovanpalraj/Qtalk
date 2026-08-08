import json
import shutil
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query, File, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel
from sqlalchemy import or_, and_, ilike

# Firebase Admin SDK for Push Notifications (Optional import check)
try:
    from firebase_admin import messaging
except ImportError:
    messaging = None

from app.database import get_db
from app.auth.models import User
from app.chat.models import Message, MessageReaction, Group, GroupMember, MessageReceipt, UserStatus
from app.chat.manager import manager

router = APIRouter(tags=["Chat Core & Real-time & Advanced Production Features"])


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


class PinMessageSchema(BaseModel):
    user_id: int
    is_pinned: bool


class StatusCreateSchema(BaseModel):
    user_id: int
    media_url: Optional[str] = None
    caption: Optional[str] = None


# ------------------------------------------------------------------
# 🟢 2. FETCH CHAT HISTORY API
# ------------------------------------------------------------------
@router.get("/messages/{user_id}/{other_id}")
def get_chat_history(user_id: int, other_id: int, db: Session = Depends(get_db)):
    """
    Iruvarukku idaiyeana chat history-ai database-il irunthu eduthu tharum API.
    """
    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        )
    ).order_by(Message.created_at.asc()).all()
    
    return messages


# ------------------------------------------------------------------
# 🟢 3. VOICE NOTE UPLOAD ENDPOINT (Audio Recording Engine)
# ------------------------------------------------------------------
@router.post("/upload/voice", tags=["Media Handling"])
async def upload_voice_note(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Frontend-il record seiyum voice memo audio file-ah (webm/mp3) server-il save seiyum.
    """
    try:
        file_ext = file.filename.split(".")[-1] if "." in file.filename else "webm"
        filename = f"voice_{uuid.uuid4()}.{file_ext}"
        file_path = f"static/voices/{filename}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        media_url = f"/static/voices/{filename}"
        return {"success": True, "media_url": media_url, "msg_type": "voice"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# 🟢 4. ADVANCED FEATURES: SEARCH, PINNING & GALLERY APIS
# ------------------------------------------------------------------
@router.get("/messages/search/{user_id}/{other_id}")
def search_chat_messages(
    user_id: int, 
    other_id: int, 
    query: str = Query(..., min_length=1), 
    db: Session = Depends(get_db)
):
    """
    Keywords-ai vachu chat history-ai search seiyum API.
    """
    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        ),
        Message.content.ilike(f"%{query}%"),
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.asc()).all()

    return {"success": True, "count": len(messages), "messages": messages}


@router.put("/message/pin/{message_id}", tags=["Chat Actions"])
def pin_unpin_message(message_id: int, data: PinMessageSchema, db: Session = Depends(get_db)):
    """
    Oru message-ah pin seiyvatharku allathu unpin seiyvatharku.
    """
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.is_pinned = data.is_pinned
    db.commit()
    
    status_text = "pinned" if data.is_pinned else "unpinned"
    return {"success": True, "message_id": message_id, "status": status_text}


@router.get("/messages/pinned/{user_id}/{other_id}")
def get_pinned_messages(user_id: int, other_id: int, db: Session = Depends(get_db)):
    """
    Iruvarukku idaiyeana pinned messages-ai mattum eduthu tharum.
    """
    pinned_msgs = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        ),
        Message.is_pinned == True,
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.desc()).all()

    return {"success": True, "pinned_messages": pinned_msgs}


# --- NEW FEATURE 1: GROUP MESSAGE READ RECEIPTS API ---
@router.get("/message/receipts/{message_id}", tags=["Group Read Receipts"])
def get_message_receipts(message_id: int, db: Session = Depends(get_db)):
    """
    Oru group message-ah yaru-yaru deliver aagivittathu matrum read seithurukanga-nu check seiyum.
    """
    receipts = db.query(MessageReceipt).filter(MessageReceipt.message_id == message_id).all()
    return {"success": True, "receipts": receipts}


# --- NEW FEATURE 2: SHARED MEDIA & LINKS GALLERY APIS ---
@router.get("/chat/gallery/{user_id}/{other_id}", tags=["Media Gallery"])
def get_shared_media(
    user_id: int, 
    other_id: int, 
    media_type: str = Query("image", description="image, video, document, link, voice"), 
    db: Session = Depends(get_db)
):
    """
    Private chat-il anuppina media files illati links-ah filter panni eduthu tharum.
    """
    query_filter = Message.msg_type == media_type
    if media_type == "link":
        query_filter = Message.content.ilike("%http%")

    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        ),
        query_filter,
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.desc()).all()

    return {"success": True, "media_type": media_type, "items": messages}


@router.get("/group/gallery/{group_id}", tags=["Media Gallery"])
def get_group_shared_media(
    group_id: int, 
    media_type: str = Query("image"), 
    db: Session = Depends(get_db)
):
    """
    Group-il anuppina media files illati links-ah filter seiyum.
    """
    query_filter = Message.msg_type == media_type
    if media_type == "link":
        query_filter = Message.content.ilike("%http%")

    messages = db.query(Message).filter(
        Message.group_id == group_id,
        query_filter,
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.desc()).all()

    return {"success": True, "group_id": group_id, "media_type": media_type, "items": messages}


# --- NEW FEATURE 3: USER STATUS / STORIES APIS ---
@router.post("/status/create", tags=["Stories"])
def create_user_status(data: StatusCreateSchema, db: Session = Depends(get_db)):
    """
    User oru pudhiya 24-hour status/story-ah post seiyvatharku.
    """
    new_status = UserStatus(
        user_id=data.user_id,
        media_url=data.media_url,
        caption=data.caption
    )
    db.add(new_status)
    db.commit()
    db.refresh(new_status)
    return {"success": True, "message": "Status posted successfully", "status_id": new_status.id}


@router.get("/statuses/active", tags=["Stories"])
def get_active_statuses(db: Session = Depends(get_db)):
    """
    Innum 24 hours expiry aagatha active user statuses-ai fetch seiyum.
    """
    now = datetime.utcnow()
    active_statuses = db.query(UserStatus).filter(UserStatus.expires_at > now).order_by(UserStatus.created_at.desc()).all()
    return {"success": True, "statuses": active_statuses}


# ------------------------------------------------------------------
# 🟢 5. WEBSOCKET REAL-TIME ENDPOINT (E2EE, Push Notifications & Group Receipts)
# ------------------------------------------------------------------
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):
    """
    Real-time WebSocket endpoint: Handles direct messages, group chats,
    typing indicators, read receipts, reactions, E2EE payloads, and WebRTC calls.
    """
    await manager.connect(user_id, websocket)

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            event = data.get("event") or data.get("type")

            # A. SEND MESSAGE (Direct, Group, E2EE Encrypted Payload, Voice/Media)
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
                    is_forwarded=data.get("is_forwarded", False),
                    status="delivered" if (receiver_id and manager.is_user_online(receiver_id)) else "sent"
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                # If group message, initialize default 'delivered' receipts for all members except sender
                if group_id:
                    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
                    for m in members:
                        if m.user_id != user_id:
                            receipt = MessageReceipt(message_id=new_msg.id, user_id=m.user_id, status="delivered")
                            db.add(receipt)
                    db.commit()

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
                    "is_forwarded": new_msg.is_forwarded,
                    "created_at": new_msg.created_at.isoformat()
                }

                if group_id:
                    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
                    member_ids = [m.user_id for m in members]
                    await manager.broadcast_to_users(payload, member_ids, exclude_sender_id=user_id)
                elif receiver_id:
                    if manager.is_user_online(receiver_id):
                        await manager.send_personal_message(payload, receiver_id)
                    else:
                        # Send Push Notification via FCM if receiver is offline
                        receiver_user = db.query(User).filter(User.id == receiver_id).first()
                        if receiver_user and receiver_user.fcm_token and messaging:
                            try:
                                fcm_msg = messaging.Message(
                                    notification=messaging.Notification(
                                        title="New Message",
                                        body="You received a new message" if new_msg.msg_type != "voice" else "You received a voice note",
                                    ),
                                    data={"sender_id": str(user_id), "chat_type": "direct"},
                                    token=receiver_user.fcm_token,
                                )
                                messaging.send(fcm_msg)
                            except Exception as fcm_err:
                                print(f"FCM Notification Error: {fcm_err}")

                    await manager.send_personal_message(payload, user_id)

            # B. TYPING INDICATOR
            elif event == "typing":
                target_id = data.get("receiver_id")
                is_typing = data.get("is_typing", True)
                if target_id:
                    await manager.send_typing_indicator(user_id, target_id, is_typing)

            # C. MARK AS READ (Blue Ticks & Group Receipts Update)
            elif event == "mark_read":
                msg_ids = data.get("message_ids", [])
                if msg_ids:
                    db.query(Message).filter(Message.id.in_(msg_ids)).update(
                        {"status": "read"}, synchronize_session=False
                    )
                    
                    # Update group receipts to 'read' if group message read
                    db.query(MessageReceipt).filter(
                        MessageReceipt.message_id.in_(msg_ids),
                        MessageReceipt.user_id == user_id
                    ).update({"status": "read"}, synchronize_session=False)
                    
                    db.commit()

                    sender_id = data.get("sender_id")
                    if sender_id:
                        await manager.send_personal_message(
                            {"event": "read_ack", "message_ids": msg_ids, "read_by": user_id},
                            sender_id
                        )

            # D. EMOJI REACTIONS
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

            # E. WEBRTC CALL SIGNALING
            elif event in ["call_offer", "call_answer", "ice_candidate", "end_call"]:
                target_id = data.get("target_id")
                if target_id:
                    data["sender_id"] = user_id
                    await manager.send_personal_message(data, target_id)

    except WebSocketDisconnect:
        manager.disconnect(user_id)


# ------------------------------------------------------------------
# 🟢 6. GROUP MANAGEMENT ENDPOINTS
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
# 🟢 7. MESSAGE ACTIONS (Edit, Delete, etc.)
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
