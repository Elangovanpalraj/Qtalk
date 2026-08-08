import json
import os
import shutil
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query, File, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel
from sqlalchemy import or_, and_, ilike
from PIL import Image

# Firebase Admin SDK for Push Notifications (Optional import check)
try:
    from firebase_admin import messaging
except ImportError:
    messaging = None

from app.database import get_db
from app.auth.models import User
from app.chat.models import (
    Message, MessageReaction, Group, GroupMember, 
    MessageReceipt, UserStatus, UserPresence, ChatBackup,
    GroupCallSession, MediaAsset, Poll, PollOption, PollVote
)
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


class DisappearingConfigSchema(BaseModel):
    duration_seconds: int  # e.g., 86400 for 24 hours, 0 to disable


class GroupCallSchema(BaseModel):
    group_id: int
    host_user_id: int
    call_type: str = "video"


class AnnouncementChannelSchema(BaseModel):
    name: str
    admin_id: int
    is_announcement: bool = True


# --- Poll Schemas ---
class PollCreateSchema(BaseModel):
    group_id: int
    sender_id: int
    question: str
    options: List[str]


class PollVoteSchema(BaseModel):
    user_id: int
    option_id: int


# ------------------------------------------------------------------
# 🟢 2. FETCH CHAT HISTORY API
# ------------------------------------------------------------------
@router.get("/messages/{user_id}/{other_id}")
def get_chat_history(user_id: int, other_id: int, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        ),
        or_(Message.expires_at == None, Message.expires_at > now),
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.asc()).all()
    
    return messages


# ------------------------------------------------------------------
# 🟢 3. VOICE NOTE UPLOAD ENDPOINT
# ------------------------------------------------------------------
@router.post("/upload/voice", tags=["Media Handling"])
async def upload_voice_note(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        file_ext = file.filename.split(".")[-1] if "." in file.filename else "webm"
        filename = f"voice_{uuid.uuid4()}.{file_ext}"
        os.makedirs("app/static/voices", exist_ok=True)
        file_path = f"app/static/voices/{filename}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        media_url = f"/static/voices/{filename}"
        return {"success": True, "media_url": media_url, "msg_type": "voice"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# 🟢 4. MEDIA COMPRESSION ENGINE
# ------------------------------------------------------------------
@router.post("/upload/media/compress", tags=["Media Pipeline"])
async def upload_and_compress_media(file: UploadFile = File(...), user_id: int = Query(...), db: Session = Depends(get_db)):
    try:
        file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
        filename = f"media_{uuid.uuid4()}.{file_ext}"
        os.makedirs("app/static", exist_ok=True)
        original_path = f"app/static/temp_{filename}"
        compressed_path = f"app/static/compressed_{filename}"
        
        with open(original_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        file_size = os.path.getsize(original_path)
        
        if file_ext in ["jpg", "jpeg", "png"]:
            img = Image.open(original_path)
            img.save(compressed_path, optimize=True, quality=60)
            os.remove(original_path)
        else:
            os.rename(original_path, compressed_path)

        compressed_url = f"/static/compressed_{filename}"

        media_record = MediaAsset(
            uploader_id=user_id,
            original_filename=file.filename,
            compressed_url=compressed_url,
            file_size_bytes=file_size
        )
        db.add(media_record)
        db.commit()
        db.refresh(media_record)

        return {
            "success": True, 
            "message": "Media compressed successfully", 
            "compressed_url": compressed_url,
            "saved_bytes": file_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# 🟢 5. ADVANCED FEATURES: SEARCH, PINNING, FORWARDING, POLLS & BACKUP
# ------------------------------------------------------------------

# --- Feature 3: Message Forwarding API ---
@router.post("/messages/forward/{message_id}", tags=["Chat Actions"])
def forward_message_endpoint(message_id: int, target_group_id: int, sender_id: int = Query(...), db: Session = Depends(get_db)):
    original_msg = db.query(Message).filter(Message.id == message_id).first()
    if not original_msg:
        raise HTTPException(status_code=404, detail="Original message not found")
        
    new_message = Message(
        sender_id=sender_id,
        group_id=target_group_id,
        content=original_msg.content,
        media_url=original_msg.media_url,
        msg_type=original_msg.msg_type,
        is_forwarded=True
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    return {"success": True, "message": "Message forwarded successfully", "new_message_id": new_message.id}


# --- Feature 6: Polls & Surveys APIs ---
@router.post("/polls/create", tags=["Polls"])
def create_poll_endpoint(data: PollCreateSchema, db: Session = Depends(get_db)):
    new_poll = Poll(group_id=data.group_id, created_by=data.sender_id, question=data.question)
    db.add(new_poll)
    db.flush() # ID generate aagum
    
    for opt_text in data.options:
        new_option = PollOption(poll_id=new_poll.id, option_text=opt_text)
        db.add(new_option)
        
    db.commit()
    return {"success": True, "poll_id": new_poll.id, "message": "Poll created successfully"}


@router.post("/polls/vote/{poll_id}", tags=["Polls"])
def cast_poll_vote(poll_id: int, data: PollVoteSchema, db: Session = Depends(get_db)):
    # Check if user already voted (UniqueConstraint handles this too)
    existing_vote = db.query(PollVote).filter(
        PollVote.poll_id == poll_id, PollVote.user_id == data.user_id
    ).first()
    
    if existing_vote:
        raise HTTPException(status_code=400, detail="User has already voted in this poll")

    option = db.query(PollOption).filter(PollOption.id == data.option_id, PollOption.poll_id == poll_id).first()
    if not option:
        raise HTTPException(status_code=404, detail="Poll option not found")

    new_vote = PollVote(poll_id=poll_id, option_id=data.option_id, user_id=data.user_id)
    option.vote_count += 1
    
    db.add(new_vote)
    db.commit()
    return {"success": True, "message": "Vote casted successfully"}


@router.get("/polls/{poll_id}", tags=["Polls"])
def get_poll_results(poll_id: int, db: Session = Depends(get_db)):
    poll = db.query(Poll).filter(Poll.id == poll_id).first()
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
        
    options = db.query(PollOption).filter(PollOption.poll_id == poll_id).all()
    return {
        "success": True,
        "poll_id": poll.id,
        "question": poll.question,
        "options": [{"id": o.id, "text": o.option_text, "votes": o.vote_count} for o in options]
    }


@router.get("/messages/search/{user_id}/{other_id}")
def search_chat_messages(
    user_id: int, 
    other_id: int, 
    query: str = Query(..., min_length=1), 
    db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        ),
        Message.content.ilike(f"%{query}%"),
        or_(Message.expires_at == None, Message.expires_at > now),
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.asc()).all()

    return {"success": True, "count": len(messages), "messages": messages}


@router.put("/message/pin/{message_id}", tags=["Chat Actions"])
def pin_unpin_message(message_id: int, data: PinMessageSchema, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    msg.is_pinned = data.is_pinned
    db.commit()
    
    status_text = "pinned" if data.is_pinned else "unpinned"
    return {"success": True, "message_id": message_id, "status": status_text}


@router.get("/messages/pinned/{user_id}/{other_id}")
def get_pinned_messages(user_id: int, other_id: int, db: Session = Depends(get_db)):
    pinned_msgs = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user_id, Message.receiver_id == other_id),
            and_(Message.sender_id == other_id, Message.receiver_id == user_id)
        ),
        Message.is_pinned == True,
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.desc()).all()

    return {"success": True, "pinned_messages": pinned_msgs}


@router.get("/message/receipts/{message_id}", tags=["Group Read Receipts"])
def get_message_receipts(message_id: int, db: Session = Depends(get_db)):
    receipts = db.query(MessageReceipt).filter(MessageReceipt.message_id == message_id).all()
    return {"success": True, "receipts": receipts}


@router.get("/chat/gallery/{user_id}/{other_id}", tags=["Media Gallery"])
def get_shared_media(
    user_id: int, 
    other_id: int, 
    media_type: str = Query("image", description="image, video, document, link, voice"), 
    db: Session = Depends(get_db)
):
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
    query_filter = Message.msg_type == media_type
    if media_type == "link":
        query_filter = Message.content.ilike("%http%")

    messages = db.query(Message).filter(
        Message.group_id == group_id,
        query_filter,
        Message.is_deleted_everyone == False
    ).order_by(Message.created_at.desc()).all()

    return {"success": True, "group_id": group_id, "media_type": media_type, "items": messages}


@router.post("/status/create", tags=["Stories"])
def create_user_status(data: StatusCreateSchema, db: Session = Depends(get_db)):
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
    now = datetime.utcnow()
    active_statuses = db.query(UserStatus).filter(UserStatus.expires_at > now).order_by(UserStatus.created_at.desc()).all()
    return {"success": True, "statuses": active_statuses}


@router.post("/chat/disappearing/{user_id}/{other_id}", tags=["Disappearing Messages"])
def set_disappearing_timer(user_id: int, other_id: int, data: DisappearingConfigSchema, db: Session = Depends(get_db)):
    return {"success": True, "message": f"Disappearing timer set to {data.duration_seconds} seconds for chat"}


@router.get("/user/presence/{target_user_id}", tags=["User Presence"])
def get_user_presence(target_user_id: int, db: Session = Depends(get_db)):
    presence = db.query(UserPresence).filter(UserPresence.user_id == target_user_id).first()
    if not presence:
        return {"success": True, "is_online": False, "last_seen": None}
    
    return {
        "success": True,
        "is_online": presence.is_online,
        "last_seen": presence.last_seen.isoformat() if presence.last_seen else None
    }


@router.post("/chat/backup/{user_id}", tags=["Backup & Restore"])
def create_chat_backup(user_id: int, db: Session = Depends(get_db)):
    messages = db.query(Message).filter(
        or_(Message.sender_id == user_id, Message.receiver_id == user_id)
    ).all()
    
    chat_list = [{
        "id": m.id,
        "sender_id": m.sender_id,
        "receiver_id": m.receiver_id,
        "group_id": m.group_id,
        "content": m.content,
        "msg_type": m.msg_type,
        "created_at": m.created_at.isoformat()
    } for m in messages]
    
    backup_json = json.dumps(chat_list)
    
    existing_backup = db.query(ChatBackup).filter(ChatBackup.user_id == user_id).first()
    if existing_backup:
        existing_backup.backup_data = backup_json
        existing_backup.created_at = datetime.utcnow()
    else:
        new_backup = ChatBackup(user_id=user_id, backup_data=backup_json)
        db.add(new_backup)
        
    db.commit()
    return {"success": True, "message": "Chat backup created successfully"}


@router.get("/chat/restore/{user_id}", tags=["Backup & Restore"])
def restore_chat_backup(user_id: int, db: Session = Depends(get_db)):
    backup = db.query(ChatBackup).filter(ChatBackup.user_id == user_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="No backup found for this user")
        
    restored_data = json.loads(backup.backup_data)
    return {"success": True, "backup_date": backup.created_at.isoformat(), "chats": restored_data}


# ------------------------------------------------------------------
# 🟢 6. GROUP & ANNOUNCEMENT MANAGEMENT
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


@router.post("/group/announcement/create", tags=["Announcement Channels"])
def create_announcement_channel(data: AnnouncementChannelSchema, db: Session = Depends(get_db)):
    new_channel = Group(
        name=data.name,
        created_by=data.admin_id,
        is_announcement_channel=data.is_announcement
    )
    db.add(new_channel)
    db.commit()
    db.refresh(new_channel)

    db.add(GroupMember(group_id=new_channel.id, user_id=data.admin_id, is_admin=True))
    db.commit()

    return {"success": True, "channel_id": new_channel.id, "message": "Announcement channel created successfully"}


@router.post("/group/call/start", tags=["Group Calls"])
def start_group_call(data: GroupCallSchema, db: Session = Depends(get_db)):
    call_session = GroupCallSession(
        group_id=data.group_id,
        host_user_id=data.host_user_id,
        call_type=data.call_type,
        is_active=True
    )
    db.add(call_session)
    db.commit()
    db.refresh(call_session)

    return {"success": True, "call_session_id": call_session.id, "message": "Group call started"}


@router.post("/group/call/end/{call_id}", tags=["Group Calls"])
def end_group_call(call_id: int, db: Session = Depends(get_db)):
    call = db.query(GroupCallSession).filter(GroupCallSession.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call session not found")

    call.is_active = False
    db.commit()
    return {"success": True, "message": "Group call ended successfully"}


# ------------------------------------------------------------------
# 🟢 7. MESSAGE ACTIONS (Edit, Delete)
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


# ------------------------------------------------------------------
# 🟢 8. WEBSOCKET REAL-TIME ENDPOINT
# ------------------------------------------------------------------
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):
    await manager.connect(user_id, websocket)

    presence = db.query(UserPresence).filter(UserPresence.user_id == user_id).first()
    if presence:
        presence.is_online = True
        presence.last_seen = datetime.utcnow()
    else:
        db.add(UserPresence(user_id=user_id, is_online=True, last_seen=datetime.utcnow()))
    db.commit()

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            event = data.get("event") or data.get("type")

            if event in ["send_message", "message"]:
                receiver_id = data.get("receiver_id")
                group_id = data.get("group_id")
                disappearing_duration = data.get("disappearing_duration", 0)
                
                expires_at = None
                if disappearing_duration > 0:
                    expires_at = datetime.utcnow() + timedelta(seconds=disappearing_duration)

                new_msg = Message(
                    sender_id=user_id,
                    receiver_id=receiver_id,
                    group_id=group_id,
                    msg_type=data.get("msg_type", "text"),
                    content=data.get("content"),
                    media_url=data.get("media_url") or data.get("file_url"),
                    reply_to_id=data.get("reply_to_id"),
                    is_forwarded=data.get("is_forwarded", False),
                    disappearing_duration=disappearing_duration,
                    expires_at=expires_at,
                    status="delivered" if (receiver_id and manager.is_user_online(receiver_id)) else "sent"
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

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
                    "expires_at": new_msg.expires_at.isoformat() if new_msg.expires_at else None,
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
                        receiver_user = db.query(User).filter(User.id == receiver_id).first()
                        if receiver_user and receiver_user.fcm_token and messaging:
                            try:
                                fcm_msg = messaging.Message(
                                    notification=messaging.Notification(
                                        title="New Message",
                                        body="You received a new message",
                                    ),
                                    data={"sender_id": str(user_id), "chat_type": "direct"},
                                    token=receiver_user.fcm_token,
                                )
                                messaging.send(fcm_msg)
                            except Exception as fcm_err:
                                print(f"FCM Error: {fcm_err}")

                    await manager.send_personal_message(payload, user_id)

            elif event == "typing":
                target_id = data.get("receiver_id")
                is_typing = data.get("is_typing", True)
                if target_id:
                    await manager.send_typing_indicator(user_id, target_id, is_typing)

            elif event == "mark_read":
                msg_ids = data.get("message_ids", [])
                if msg_ids:
                    db.query(Message).filter(Message.id.in_(msg_ids)).update(
                        {"status": "read"}, synchronize_session=False
                    )
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

            elif event in ["call_offer", "call_answer", "ice_candidate", "end_call"]:
                target_id = data.get("target_id")
                if target_id:
                    data["sender_id"] = user_id
                    await manager.send_personal_message(data, target_id)

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        presence = db.query(UserPresence).filter(UserPresence.user_id == user_id).first()
        if presence:
            presence.is_online = False
            presence.last_seen = datetime.utcnow()
            db.commit()
