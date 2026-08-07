import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, File, UploadFile
from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text, create_engine
from sqlalchemy.orm import Session, relationship
from pydantic import BaseModel
from app.database import Base, engine, get_db

# ------------------------------------------------------------------
# 🟢 1. ENHANCED DATABASE MODELS (All WhatsApp Features Supported)
# ------------------------------------------------------------------
class User(Base):
    __tablename__ = "users_v2"
    phone = Column(String, primary_key=True, index=True)
    name = Column(String)
    public_key = Column(Text, nullable=True) # For E2EE (End-to-End Encryption)
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, default=datetime.utcnow)

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    admin_phone = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    user_phone = Column(String)

class Message(Base):
    __tablename__ = "messages_v2"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender = Column(String, index=True)
    receiver = Column(String, nullable=True, index=True) # None if group
    group_id = Column(Integer, nullable=True, index=True)
    
    msg_type = Column(String, default="text") # text, image, video, voice, doc, location, contact
    content = Column(Text)                    # Text or Encrypted Payload
    file_url = Column(String, nullable=True)
    
    # Status: 'sent' (✓), 'delivered' (✓✓ grey), 'read' (✓✓ blue)
    status = Column(String, default="sent") 
    
    reply_to_id = Column(Integer, nullable=True)
    is_edited = Column(Boolean, default=False)
    is_deleted_everyone = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Reaction(Base):
    __tablename__ = "message_reactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages_v2.id"))
    user_phone = Column(String)
    emoji = Column(String)

class DeleteForMe(Base):
    __tablename__ = "deleted_for_me"
    id = Column(Integer, primary_primary=True, autoincrement=True)
    message_id = Column(Integer)
    user_phone = Column(String)

Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="", tags=["Chat Core"])

# ------------------------------------------------------------------
# 🟢 2. WEBSOCKET CONNECTION MANAGER
# ------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, phone: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[phone] = websocket

    def disconnect(self, phone: str):
        if phone in self.active_connections:
            del self.active_connections[phone]

    async def send_personal(self, data: dict, recipient_phone: str):
        if recipient_phone in self.active_connections:
            await self.active_connections[recipient_phone].send_text(json.dumps(data))

    async def broadcast_to_group(self, data: dict, member_phones: List[str]):
        for phone in member_phones:
            if phone in self.active_connections:
                await self.active_connections[phone].send_text(json.dumps(data))

manager = ConnectionManager()

# ------------------------------------------------------------------
# 🟢 3. REAL-TIME WEBSOCKET ENDPOINT
# ------------------------------------------------------------------
@websocket_router := APIRouter()
@router.websocket("/ws/{phone}")
async def websocket_endpoint(websocket: WebSocket, phone: str, db: Session = Depends(get_db)):
    await manager.connect(phone, websocket)
    
    # Update online status
    user = db.query(User).filter(User.phone == phone).first()
    if user:
        user.is_online = True
        db.commit()

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            action_type = data.get("type")

            # A. TYPING INDICATOR
            if action_type == "typing":
                target = data.get("receiver")
                await manager.send_personal({
                    "type": "typing",
                    "sender": phone,
                    "is_typing": data.get("is_typing")
                }, target)

            # B. SEND MESSAGE (Text, Media, Voice, Location)
            elif action_type == "message":
                receiver = data.get("receiver")
                group_id = data.get("group_id")
                
                new_msg = Message(
                    sender=phone,
                    receiver=receiver,
                    group_id=group_id,
                    msg_type=data.get("msg_type", "text"),
                    content=data.get("content"),
                    file_url=data.get("file_url"),
                    reply_to_id=data.get("reply_to_id"),
                    status="delivered" if receiver in manager.active_connections else "sent"
                )
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                payload = {
                    "type": "new_message",
                    "id": new_msg.id,
                    "sender": phone,
                    "receiver": receiver,
                    "group_id": group_id,
                    "msg_type": new_msg.msg_type,
                    "content": new_msg.content,
                    "file_url": new_msg.file_url,
                    "status": new_msg.status,
                    "reply_to_id": new_msg.reply_to_id,
                    "timestamp": new_msg.timestamp.strftime("%I:%M %p")
                }

                if group_id:
                    members = db.query(GroupMember.user_phone).filter(GroupMember.group_id == group_id).all()
                    m_list = [m[0] for m in members if m[0] != phone]
                    await manager.broadcast_to_group(payload, m_list)
                elif receiver:
                    await manager.send_personal(payload, receiver)
                    await manager.send_personal(payload, phone) # Self ack

            # C. MESSAGE READ TICK UPDATE (Grey -> Blue Tick)
            elif action_type == "mark_read":
                msg_ids = data.get("message_ids", [])
                db.query(Message).filter(Message.id.in_(msg_ids)).update({"status": "read"}, synchronize_session=False)
                db.commit()
                sender_phone = data.get("sender_phone")
                await manager.send_personal({"type": "read_ack", "message_ids": msg_ids}, sender_phone)

            # D. EMOJI REACTION
            elif action_type == "reaction":
                msg_id = data.get("message_id")
                emoji = data.get("emoji")
                react = Reaction(message_id=msg_id, user_phone=phone, emoji=emoji)
                db.add(react)
                db.commit()
                
                target_user = data.get("receiver")
                await manager.send_personal({
                    "type": "reaction",
                    "message_id": msg_id,
                    "emoji": emoji,
                    "user_phone": phone
                }, target_user)

    except WebSocketDisconnect:
        manager.disconnect(phone)
        u = db.query(User).filter(User.phone == phone).first()
        if u:
            u.is_online = False
            u.last_seen = datetime.utcnow()
            db.commit()

# ------------------------------------------------------------------
# 🟢 4. GROUP & EDIT API ENDPOINTS
# ------------------------------------------------------------------
class GroupCreateSchema(BaseModel):
    name: str
    admin_phone: str
    members: List[str] # Up to 1024 numbers

@router.post("/group/create")
def create_group(data: GroupCreateSchema, db: Session = Depends(get_db)):
    if len(data.members) > 1024:
        raise HTTPException(status_code=400, detail="Group capacity exceeded (Max 1024)")
    
    new_group = Group(name=data.name, admin_phone=data.admin_phone)
    db.add(new_group)
    db.commit()
    db.refresh(new_group)

    # Add Admin + Members
    all_members = list(set(data.members + [data.admin_phone]))
    for m in all_members:
        db.add(GroupMember(group_id=new_group.id, user_phone=m))
    db.commit()

    return {"success": True, "group_id": new_group.id, "message": f"Group '{data.name}' created!"}

class EditMessageSchema(BaseModel):
    message_id: int
    user_phone: str
    new_content: str

@router.put("/message/edit")
def edit_message(data: EditMessageSchema, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == data.message_id, Message.sender == data.user_phone).first()
    if not msg:
        return {"success": False, "message": "Message not found or permission denied"}

    # 15-Minute Window Check
    if datetime.utcnow() - msg.timestamp > timedelta(minutes=15):
        return {"success": False, "message": "Edit time window (15 mins) expired!"}

    msg.content = data.new_content
    msg.is_edited = True
    db.commit()
    return {"success": True, "message": "Message edited successfully"}
