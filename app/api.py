from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from collections import defaultdict, deque
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import or_, and_, func, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, MAX_UPLOAD_MB, SEARCH_RESULT_LIMIT
from app.database import get_db
from app.models import (
    User, Contact, Chat, Message, MessageClientKey, MessageDelivery,
    MessageReaction, ReadReceipt, MessageEdit, MessageStar, MessagePin,
    Status, StatusView, ChatUserSetting, Block, GroupMemberMeta,
    DirectChatKey, group_members,
)
from app.security import bearer, get_user_id
from app.realtime import manager


def utc_iso(value):
    """Serialize the database UTC timestamp as an explicit UTC ISO-8601 value."""
    if value is None:
        return None
    return value.replace(tzinfo=__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")

router = APIRouter(prefix="/api", tags=["api"])
_search_hits = defaultdict(deque)

def normalize_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")

def normalize_phone_digits(value: str) -> str:
    digits = normalize_digits(value)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits

def phone_matches(stored: str, query: str) -> bool:
    a, b = normalize_phone_digits(stored), normalize_phone_digits(query)
    return bool(a and b and (a == b or a.endswith(b) or b.endswith(a)))

def current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    # Prefer Authorization, but keep a secure HttpOnly session cookie as a
    # fallback so a normal browser restart does not force a new OTP login.
    if creds:
        uid = get_user_id(creds)
    else:
        cookie_token = request.cookies.get("qtalk_session")
        if not cookie_token:
            raise HTTPException(401, "Missing token")
        uid = get_user_id(HTTPAuthorizationCredentials(scheme="Bearer", credentials=cookie_token))
    user = db.get(User, uid)
    if not user:
        raise HTTPException(401, "User not found")
    return user

def chat_member_ids(chat):
    return [u.id for u in chat.members]

def is_member(chat, user_id):
    return bool(chat and user_id in chat_member_ids(chat))

def blocked_either_way(db, a, b):
    return db.query(Block).filter(
        or_(
            and_(Block.blocker_id == a, Block.blocked_id == b),
            and_(Block.blocker_id == b, Block.blocked_id == a),
        )
    ).first() is not None

def ensure_chat_setting(db, chat_id, user_id):
    row = db.query(ChatUserSetting).filter_by(chat_id=chat_id, user_id=user_id).first()
    if not row:
        row = ChatUserSetting(chat_id=chat_id, user_id=user_id)
        db.add(row)
        db.flush()
    return row

def chat_for_users(db: Session, a: int, b: int):
    key = f"{min(a,b)}:{max(a,b)}"
    keyed = db.query(DirectChatKey).filter(DirectChatKey.chat_key == key).first()
    if keyed:
        chat = db.get(Chat, keyed.chat_id)
        if chat:
            ensure_chat_setting(db, chat.id, a)
            ensure_chat_setting(db, chat.id, b)
            db.commit()
            return chat

    # Backfill key for a chat created by an older Qtalk build.
    chats = db.query(Chat).filter(Chat.kind == "direct").all()
    for c in chats:
        ids = set(chat_member_ids(c))
        if ids == {a, b}:
            try:
                db.add(DirectChatKey(chat_id=c.id, chat_key=key))
                ensure_chat_setting(db, c.id, a)
                ensure_chat_setting(db, c.id, b)
                db.commit()
            except IntegrityError:
                db.rollback()
            return c

    c = Chat(kind="direct")
    c.members = [db.get(User, a), db.get(User, b)]
    db.add(c)
    db.flush()
    db.add(DirectChatKey(chat_id=c.id, chat_key=key))
    ensure_chat_setting(db, c.id, a)
    ensure_chat_setting(db, c.id, b)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(DirectChatKey).filter(DirectChatKey.chat_key == key).first()
        if existing:
            return db.get(Chat, existing.chat_id)
        raise
    db.refresh(c)
    return c

def msg_json(db: Session, m: Message, me_id: int):
    reactions = db.query(MessageReaction).filter(MessageReaction.message_id == m.id).all()
    chat = db.get(Chat, m.chat_id)
    recipient_ids = [uid for uid in chat_member_ids(chat) if uid != m.sender_id] if chat else []
    delivered_ids = {row.user_id for row in db.query(MessageDelivery).filter(MessageDelivery.message_id == m.id).all()}
    read_ids = {row.user_id for row in db.query(ReadReceipt).filter(ReadReceipt.message_id == m.id).all()}
    # For a direct chat there is exactly one recipient. For groups, WhatsApp-style
    # ticks become double only after every other member has received the message,
    # and blue only after every other member has read it.
    delivered_count = len(delivered_ids.intersection(recipient_ids))
    read_count = len(read_ids.intersection(recipient_ids))
    all_delivered = bool(recipient_ids) and delivered_count == len(recipient_ids)
    all_read = bool(recipient_ids) and read_count == len(recipient_ids)
    starred = db.query(MessageStar).filter(MessageStar.message_id == m.id, MessageStar.user_id == me_id).first() is not None
    pinned = db.query(MessagePin).filter(MessagePin.message_id == m.id).first() is not None
    edited = db.query(MessageEdit).filter(MessageEdit.message_id == m.id).first() is not None
    reply_preview = None
    if m.reply_to_id:
        rm = db.get(Message, m.reply_to_id)
        if rm:
            sender = db.get(User, rm.sender_id)
            reply_preview = {
                "id": rm.id,
                "sender_name": sender.name if sender else "Unknown",
                "text": None if rm.deleted_at else (rm.text or ("📎 Media" if rm.media_url else "")),
                "deleted": bool(rm.deleted_at),
            }
    return {
        "id": m.id, "chat_id": m.chat_id, "sender_id": m.sender_id,
        "text": None if m.deleted_at else m.text,
        "media_url": None if m.deleted_at else m.media_url,
        "media_type": None if m.deleted_at else m.media_type,
        "file_name": None if m.deleted_at else m.file_name,
        "reply_to_id": m.reply_to_id,
        "reply_preview": reply_preview,
        "created_at": utc_iso(m.created_at),
        "deleted": bool(m.deleted_at),
        "edited": edited,
        "delivered": all_delivered,
        "delivered_count": delivered_count,
        "read": all_read,
        "read_count": read_count,
        "starred": starred,
        "pinned": pinned,
        "reactions": [{"emoji": r.emoji, "user_id": r.user_id} for r in reactions],
        "mine": m.sender_id == me_id,
    }

def user_json(u: User):
    return {
        "id": u.id, "phone": u.phone, "name": u.name, "about": u.about,
        "avatar_url": u.avatar_url, "is_online": manager.online(u.id),
        "last_seen": utc_iso(u.last_seen),
    }

class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    about: str = Field(default="", max_length=255)

class ContactIn(BaseModel):
    phone: str
    nickname: str | None = None

class MessageIn(BaseModel):
    chat_id: int
    text: str | None = None
    reply_to_id: int | None = None
    client_id: str | None = Field(default=None, max_length=80)

class EditIn(BaseModel):
    text: str = Field(min_length=1, max_length=10000)

class ReactionIn(BaseModel):
    emoji: str = Field(min_length=1, max_length=20)

class GroupIn(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    member_ids: list[int] = Field(default_factory=list)

class GroupMembersIn(BaseModel):
    member_ids: list[int] = Field(default_factory=list)

class StatusIn(BaseModel):
    text: str | None = None
    background: str = "#075E54"

class ChatSettingIn(BaseModel):
    muted: bool | None = None
    archived: bool | None = None

async def broadcast_message(db, chat, message):
    payload = {"type": "message", "message": msg_json(db, message, message.sender_id)}
    await manager.send_many(chat_member_ids(chat), payload)
    return payload["message"]

def create_message_record(db: Session, user_id: int, data: MessageIn):
    c = db.get(Chat, data.chat_id)
    if not is_member(c, user_id):
        raise HTTPException(403, "Not a chat member")
    if blocked_either_way(db, user_id, next((x for x in chat_member_ids(c) if x != user_id), user_id)) and c.kind == "direct":
        raise HTTPException(403, "Messaging is blocked")
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(400, "Message is empty")
    if data.reply_to_id:
        reply = db.get(Message, data.reply_to_id)
        if not reply or reply.chat_id != c.id:
            raise HTTPException(400, "Reply target not found in this chat")

    if data.client_id:
        existing_key = db.query(MessageClientKey).filter(MessageClientKey.client_id == data.client_id).first()
        if existing_key:
            existing = db.get(Message, existing_key.message_id)
            if existing:
                return c, existing, True

    now = datetime.utcnow()
    m = Message(chat_id=c.id, sender_id=user_id, text=text, reply_to_id=data.reply_to_id)
    db.add(m)
    db.flush()

    if data.client_id:
        db.add(MessageClientKey(client_id=data.client_id, message_id=m.id))

    for uid in chat_member_ids(c):
        if uid == user_id:
            continue
        if manager.online(uid):
            db.add(MessageDelivery(message_id=m.id, user_id=uid, delivered_at=now))
    if any(manager.online(uid) for uid in chat_member_ids(c) if uid != user_id):
        m.delivered_at = now

    db.commit()
    db.refresh(m)
    return c, m, False

@router.get("/me")
def me(user=Depends(current_user)):
    return user_json(user)

@router.put("/me")
def update_me(data: ProfileIn, user=Depends(current_user), db: Session=Depends(get_db)):
    user.name = data.name.strip()
    user.about = data.about.strip()
    db.commit()
    return {"success": True, **user_json(user)}

async def save_upload(file: UploadFile):
    ext=Path(file.filename or "").suffix.lower()
    allowed={".jpg",".jpeg",".png",".gif",".webp",".mp3",".wav",".ogg",".m4a",".mp4",".webm",".pdf",".doc",".docx",".txt",".zip",".csv",".xlsx",".pptx"}
    if ext not in allowed:
        raise HTTPException(400, "File type not allowed")
    data=await file.read()
    if len(data)>MAX_UPLOAD_MB*1024*1024:
        raise HTTPException(413, f"File too large. Maximum is {MAX_UPLOAD_MB} MB")
    name=f"{uuid4().hex}{ext}"
    (UPLOAD_DIR/name).write_bytes(data)
    media_type="image" if ext in {".jpg",".jpeg",".png",".gif",".webp"} else "audio" if ext in {".mp3",".wav",".ogg",".m4a"} else "video" if ext in {".mp4",".webm"} else "document"
    return {"url":f"/uploads/{name}","media_type":media_type,"file_name":file.filename}

@router.post("/me/avatar")
async def update_avatar(file: UploadFile = File(...), user=Depends(current_user), db: Session=Depends(get_db)):
    result = await save_upload(file)
    if result["media_type"] != "image":
        raise HTTPException(400, "Avatar must be an image")
    user.avatar_url = result["url"]
    db.commit()
    return {"success": True, "avatar_url": user.avatar_url}

@router.get("/users/search")
def search_users(q: str = Query(min_length=1, max_length=120), user=Depends(current_user), db: Session=Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return []
    now = datetime.utcnow().timestamp()
    hits = _search_hits[user.id]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= 80:
        raise HTTPException(429, "Too many searches. Please wait a moment.")
    hits.append(now)

    digits = normalize_phone_digits(q)
    name_query = q.casefold()
    candidates = db.query(User).filter(User.id != user.id).limit(3000).all()
    scored=[]
    for u in candidates:
        score=0
        uname=(u.name or "").casefold()
        uphone=normalize_phone_digits(u.phone)
        if name_query and name_query in uname:
            score += 120 if uname == name_query else 60
        if digits:
            if uphone == digits:
                score += 250
            elif uphone.endswith(digits) or digits.endswith(uphone):
                score += 180
            elif len(digits) >= 4 and digits in uphone:
                score += 100
        if score:
            scored.append((score,u))
    scored.sort(key=lambda x:(-x[0], x[1].name.casefold()))
    return [user_json(u) for _,u in scored[:SEARCH_RESULT_LIMIT]]

@router.get("/users/{user_id}")
def get_user(user_id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    u=db.get(User,user_id)
    if not u or u.id==user.id: raise HTTPException(404,"User not found")
    return user_json(u)

@router.post("/contacts")
def add_contact(data: ContactIn, user=Depends(current_user), db: Session=Depends(get_db)):
    qdigits=normalize_phone_digits(data.phone)
    target=next((u for u in db.query(User).limit(5000).all() if normalize_phone_digits(u.phone)==qdigits),None)
    if not target or target.id==user.id: raise HTTPException(404,"User not found on Qtalk")
    existing=db.query(Contact).filter_by(owner_id=user.id,contact_id=target.id).first()
    if not existing:
        db.add(Contact(owner_id=user.id,contact_id=target.id,nickname=(data.nickname or "").strip() or None));db.commit()
    return {"success":True}

@router.get("/contacts")
def contacts(user=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.query(Contact).filter(Contact.owner_id==user.id).all()
    result=[]
    for r in rows:
        u=db.get(User,r.contact_id)
        if u:
            x=user_json(u);x["name"]=r.nickname or u.name;result.append(x)
    return result

@router.get("/chats")
def chats(archived:bool=False,user=Depends(current_user),db:Session=Depends(get_db)):
    out=[]
    for c in db.query(Chat).order_by(Chat.id.desc()).all():
        ids=chat_member_ids(c)
        if user.id not in ids: continue
        setting=ensure_chat_setting(db,c.id,user.id)
        if bool(setting.archived)!=archived:
            continue
        last_q=db.query(Message).filter(Message.chat_id==c.id)
        if setting.cleared_at:
            last_q=last_q.filter(Message.created_at>setting.cleared_at)
        last=last_q.order_by(Message.id.desc()).first()
        if c.kind=="group":
            title=c.title or "Group"; other=None
        else:
            other_user=next((u for u in c.members if u.id!=user.id),None)
            if not other_user: continue
            title=other_user.name;other=user_json(other_user)
        unread_q=db.query(Message).filter(
            Message.chat_id==c.id, Message.sender_id!=user.id, Message.deleted_at==None
        )
        if setting.cleared_at:
            unread_q=unread_q.filter(Message.created_at>setting.cleared_at)
        read_ids=db.query(ReadReceipt.message_id).filter(ReadReceipt.user_id==user.id)
        unread=unread_q.filter(~Message.id.in_(read_ids)).count()
        out.append({
            "id":c.id,"kind":c.kind,"title":title,"other":other,
            "last":last.text if last and not last.deleted_at else ("📎 Media" if last else ""),
            "last_at":utc_iso(last.created_at) if last else None,
            "unread":unread,"member_ids":ids,"muted":bool(setting.muted),"archived":bool(setting.archived)
        })
    db.commit()
    out.sort(key=lambda x:x["last_at"] or "",reverse=True)
    return out

@router.get("/chats/{chat_id}")
def chat_detail(chat_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id): raise HTTPException(403,"Forbidden")
    members=[]
    for u in c.members:
        meta=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=u.id).first()
        row=user_json(u)
        row["is_admin"]=bool(meta and meta.is_admin)
        members.append(row)
    my_meta=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=user.id).first()
    return {
        "id":c.id,"kind":c.kind,"title":c.title,
        "members":members,"am_admin":bool(my_meta and my_meta.is_admin),
    }

@router.post("/chats/direct/{user_id}")
def create_direct(user_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    target=db.get(User,user_id)
    if not target or target.id==user.id: raise HTTPException(404,"User not found")
    if blocked_either_way(db,user.id,target.id): raise HTTPException(403,"Messaging is blocked")
    c=chat_for_users(db,user.id,target.id)
    return {"id":c.id}

@router.post("/chats/group")
def create_group(data:GroupIn,user=Depends(current_user),db:Session=Depends(get_db)):
    ids=list(dict.fromkeys(data.member_ids+[user.id]))
    members=[db.get(User,i) for i in ids];members=[m for m in members if m]
    if len(members)<2: raise HTTPException(400,"Add at least one other member")
    c=Chat(kind="group",title=data.title.strip());c.members=members;db.add(c);db.flush()
    for m in members:
        db.add(GroupMemberMeta(chat_id=c.id,user_id=m.id,is_admin=(m.id==user.id)))
        ensure_chat_setting(db,c.id,m.id)
    db.commit();db.refresh(c)
    return {"id":c.id,"title":c.title}

@router.post("/chats/{chat_id}/members")
def add_group_members(chat_id:int,data:GroupMembersIn,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not c or c.kind!="group" or not is_member(c,user.id): raise HTTPException(404,"Group not found")
    admin=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=user.id,is_admin=True).first()
    if not admin: raise HTTPException(403,"Admin only")
    current=set(chat_member_ids(c))
    for uid in dict.fromkeys(data.member_ids):
        if uid not in current:
            target=db.get(User,uid)
            if target:
                c.members.append(target);db.add(GroupMemberMeta(chat_id=chat_id,user_id=uid,is_admin=False));ensure_chat_setting(db,chat_id,uid)
    db.commit()
    return {"success":True}

@router.delete("/chats/{chat_id}/members/{member_id}")
def remove_group_member(chat_id:int,member_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not c or c.kind!="group" or not is_member(c,user.id): raise HTTPException(404,"Group not found")
    admin=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=user.id,is_admin=True).first()
    if not admin: raise HTTPException(403,"Admin only")
    if member_id==user.id: raise HTTPException(400,"Use leave group instead")
    target=db.get(User,member_id)
    if target in c.members:
        c.members.remove(target)
    meta=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=member_id).first()
    if meta: db.delete(meta)
    db.commit()
    return {"success":True}

@router.post("/chats/{chat_id}/members/{member_id}/promote")
def promote_group_member(chat_id:int,member_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not c or c.kind!="group" or not is_member(c,user.id): raise HTTPException(404,"Group not found")
    admin=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=user.id,is_admin=True).first()
    if not admin: raise HTTPException(403,"Admin only")
    meta=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=member_id).first()
    if not meta: raise HTTPException(404,"Member not found")
    meta.is_admin=True
    db.commit()
    return {"success":True}

@router.post("/chats/{chat_id}/read")
async def mark_read(chat_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id): raise HTTPException(403,"Forbidden")
    now=datetime.utcnow()
    unread=db.query(Message).filter(
        Message.chat_id==chat_id, Message.sender_id!=user.id, Message.deleted_at==None
    ).all()
    changed=[]
    sender_ids=set()
    for m in unread:
        exists=db.query(ReadReceipt).filter_by(message_id=m.id,user_id=user.id).first()
        if not exists:
            db.add(ReadReceipt(message_id=m.id,user_id=user.id,read_at=now))
            changed.append(m.id)
            sender_ids.add(m.sender_id)
    db.commit()
    # A read receipt belongs to the reader, but the visible tick belongs to the
    # original sender. Send the event only to those senders instead of every
    # member, which prevents unrelated clients from changing their own bubbles.
    for sender_id in sender_ids:
        ids=[mid for mid in changed if db.get(Message,mid).sender_id==sender_id]
        if ids:
            await manager.send_user(sender_id,{
                "type":"read", "chat_id":chat_id, "user_id":user.id,
                "message_ids":ids,
            })
    return {"success":True,"count":len(changed)}

@router.get("/chats/{chat_id}/messages")
def messages(chat_id:int,limit:int=100,before_id:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id): raise HTTPException(403,"Not a chat member")
    setting=ensure_chat_setting(db,chat_id,user.id)
    q=db.query(Message).filter(Message.chat_id==chat_id)
    if setting.cleared_at:q=q.filter(Message.created_at>setting.cleared_at)
    if before_id:q=q.filter(Message.id<before_id)
    rows=q.order_by(Message.id.desc()).limit(min(max(limit,1),300)).all()
    return [msg_json(db,m,user.id) for m in reversed(rows)]

@router.post("/messages")
async def create_message(data:MessageIn,user=Depends(current_user),db:Session=Depends(get_db)):
    c,m,duplicate=create_message_record(db,user.id,data)
    if not duplicate:
        for recipient_id in chat_member_ids(c):
            await manager.send_user(recipient_id,{"type":"message","message":msg_json(db,m,recipient_id)})
        for recipient_id in chat_member_ids(c):
            if recipient_id != user.id and manager.online(recipient_id):
                await manager.send_user(user.id,{"type":"delivery","chat_id":c.id,"user_id":recipient_id,"message_ids":[m.id]})
    return msg_json(db,m,user.id)

class ForwardIn(BaseModel):
    chat_ids: list[int]

@router.post("/messages/{message_id}/forward")
async def forward_message(message_id:int,data:ForwardIn,user=Depends(current_user),db:Session=Depends(get_db)):
    src=db.get(Message,message_id)
    if not src or src.deleted_at: raise HTTPException(404,"Message not found")
    src_chat=db.get(Chat,src.chat_id)
    if not is_member(src_chat,user.id): raise HTTPException(403,"Forbidden")
    if not data.chat_ids: raise HTTPException(400,"Choose at least one chat")
    now=datetime.utcnow()
    sent=[]
    for target_chat_id in dict.fromkeys(data.chat_ids):
        c=db.get(Chat,target_chat_id)
        if not c or not is_member(c,user.id): continue
        if c.kind=="direct" and blocked_either_way(db,user.id,next((x for x in chat_member_ids(c) if x!=user.id),user.id)):
            continue
        m=Message(chat_id=c.id,sender_id=user.id,text=src.text,media_url=src.media_url,media_type=src.media_type,file_name=src.file_name)
        db.add(m);db.flush()
        for uid in chat_member_ids(c):
            if uid!=user.id and manager.online(uid):
                db.add(MessageDelivery(message_id=m.id,user_id=uid,delivered_at=now))
        if any(manager.online(uid) for uid in chat_member_ids(c) if uid!=user.id):
            m.delivered_at=now
        db.commit();db.refresh(m)
        for recipient_id in chat_member_ids(c):
            await manager.send_user(recipient_id,{"type":"message","message":msg_json(db,m,recipient_id)})
        sent.append(msg_json(db,m,user.id))
    return {"success":True,"sent":sent}

@router.post("/chats/{chat_id}/media")
async def media_message(chat_id:int,file:UploadFile=File(...),user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id): raise HTTPException(403,"Forbidden")
    result=await save_upload(file)
    now=datetime.utcnow()
    m=Message(chat_id=chat_id,sender_id=user.id,media_url=result["url"],media_type=result["media_type"],file_name=result["file_name"])
    db.add(m);db.flush()
    for uid in chat_member_ids(c):
        if uid!=user.id and manager.online(uid): db.add(MessageDelivery(message_id=m.id,user_id=uid,delivered_at=now))
    if any(manager.online(uid) for uid in chat_member_ids(c) if uid!=user.id):m.delivered_at=now
    db.commit();db.refresh(m)
    for recipient_id in chat_member_ids(c):
        await manager.send_user(recipient_id,{"type":"message","message":msg_json(db,m,recipient_id)})
    for recipient_id in chat_member_ids(c):
        if recipient_id != user.id and manager.online(recipient_id):
            await manager.send_user(user.id,{"type":"delivery","chat_id":c.id,"user_id":recipient_id,"message_ids":[m.id]})
    return msg_json(db,m,user.id)

@router.patch("/messages/{message_id}")
async def edit_message(message_id:int,data:EditIn,user=Depends(current_user),db:Session=Depends(get_db)):
    m=db.get(Message,message_id)
    if not m or m.sender_id!=user.id or m.deleted_at: raise HTTPException(403,"Only your active message can be edited")
    if datetime.utcnow()-m.created_at>timedelta(minutes=15): raise HTTPException(400,"Edit window expired (15 minutes)")
    old=m.text;m.text=data.text.strip()
    db.add(MessageEdit(message_id=m.id,editor_id=user.id,old_text=old,edited_at=datetime.utcnow()))
    db.commit();db.refresh(m);c=db.get(Chat,m.chat_id)
    payload=msg_json(db,m,user.id)
    await manager.send_many(chat_member_ids(c),{"type":"message_updated","message":payload})
    return payload

@router.delete("/messages/{message_id}")
async def delete_message(message_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    m=db.get(Message,message_id)
    if not m or m.sender_id!=user.id: raise HTTPException(403,"Only sender can delete")
    m.deleted_at=datetime.utcnow();db.commit();c=db.get(Chat,m.chat_id)
    await manager.send_many(chat_member_ids(c),{"type":"message_deleted","message_id":m.id})
    return {"success":True}

@router.post("/messages/{message_id}/reaction")
async def reaction(message_id:int,data:ReactionIn,user=Depends(current_user),db:Session=Depends(get_db)):
    m=db.get(Message,message_id);c=db.get(Chat,m.chat_id) if m else None
    if not m or not is_member(c,user.id): raise HTTPException(403,"Forbidden")
    old=db.query(MessageReaction).filter_by(message_id=m.id,user_id=user.id).first()
    if old and old.emoji==data.emoji:db.delete(old)
    elif old:old.emoji=data.emoji
    else:db.add(MessageReaction(message_id=m.id,user_id=user.id,emoji=data.emoji))
    db.commit()
    reactions=[{"emoji":r.emoji,"user_id":r.user_id} for r in db.query(MessageReaction).filter_by(message_id=m.id).all()]
    payload={"type":"reaction","message_id":m.id,"reactions":reactions}
    await manager.send_many(chat_member_ids(c),payload)
    return payload

@router.post("/messages/{message_id}/star")
async def star_message(message_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    m=db.get(Message,message_id);c=db.get(Chat,m.chat_id) if m else None
    if not m or not is_member(c,user.id):raise HTTPException(403,"Forbidden")
    row=db.query(MessageStar).filter_by(message_id=m.id,user_id=user.id).first()
    if row:db.delete(row);starred=False
    else:db.add(MessageStar(message_id=m.id,user_id=user.id));starred=True
    db.commit()
    await manager.send_many(chat_member_ids(c),{"type":"message_meta","message_id":m.id,"starred_by":user.id,"starred":starred})
    return {"starred":starred}

@router.post("/messages/{message_id}/pin")
async def pin_message(message_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    m=db.get(Message,message_id);c=db.get(Chat,m.chat_id) if m else None
    if not m or not is_member(c,user.id):raise HTTPException(403,"Forbidden")
    row=db.query(MessagePin).filter_by(message_id=m.id).first()
    if row:db.delete(row);pinned=False
    else:db.add(MessagePin(message_id=m.id,pinned_by=user.id));pinned=True
    db.commit()
    await manager.send_many(chat_member_ids(c),{"type":"message_meta","message_id":m.id,"pinned":pinned})
    return {"pinned":pinned}

@router.get("/chats/{chat_id}/search")
def search_chat(chat_id:int,q:str=Query(min_length=1,max_length=100),user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id):raise HTTPException(403,"Forbidden")
    setting=ensure_chat_setting(db,chat_id,user.id)
    rows=db.query(Message).filter(Message.chat_id==chat_id,Message.deleted_at==None,Message.text.ilike(f"%{q.strip()}%"))
    if setting.cleared_at:rows=rows.filter(Message.created_at>setting.cleared_at)
    return [msg_json(db,m,user.id) for m in rows.order_by(Message.id.desc()).limit(100).all()]

@router.post("/chats/{chat_id}/settings")
def chat_settings(chat_id:int,data:ChatSettingIn,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id):raise HTTPException(403,"Forbidden")
    s=ensure_chat_setting(db,chat_id,user.id)
    if data.muted is not None:s.muted=data.muted
    if data.archived is not None:s.archived=data.archived
    db.commit()
    return {"muted":s.muted,"archived":s.archived}

@router.post("/chats/{chat_id}/clear")
def clear_chat(chat_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not is_member(c,user.id):raise HTTPException(403,"Forbidden")
    s=ensure_chat_setting(db,chat_id,user.id);s.cleared_at=datetime.utcnow();db.commit()
    return {"success":True}

@router.post("/chats/{chat_id}/leave")
def leave_group(chat_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    c=db.get(Chat,chat_id)
    if not c or c.kind!="group" or not is_member(c,user.id):raise HTTPException(404,"Group not found")
    target=db.get(User,user.id);c.members.remove(target)
    meta=db.query(GroupMemberMeta).filter_by(chat_id=chat_id,user_id=user.id).first()
    if meta:db.delete(meta)
    db.commit()
    return {"success":True}

@router.post("/blocks/{user_id}")
async def block_user(user_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    target=db.get(User,user_id)
    if not target or target.id==user.id:raise HTTPException(404,"User not found")
    if not db.query(Block).filter_by(blocker_id=user.id,blocked_id=target.id).first():
        db.add(Block(blocker_id=user.id,blocked_id=target.id));db.commit()
    await manager.send_user(target.id,{"type":"blocked","by_user_id":user.id})
    return {"success":True}

@router.delete("/blocks/{user_id}")
def unblock_user(user_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    db.query(Block).filter_by(blocker_id=user.id,blocked_id=user_id).delete()
    db.commit();return {"success":True}

@router.get("/blocks")
def list_blocks(user=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.query(Block).filter_by(blocker_id=user.id).all()
    return [user_json(db.get(User,r.blocked_id)) for r in rows if db.get(User,r.blocked_id)]

@router.post("/status")
def create_status(data:StatusIn,user=Depends(current_user),db:Session=Depends(get_db)):
    bg=data.background if re.fullmatch(r"#[0-9a-fA-F]{6}",data.background or "") else "#075E54"
    text=(data.text or "").strip()
    if not text:raise HTTPException(400,"Status text is empty")
    s=Status(user_id=user.id,text=text,background=bg,expires_at=datetime.utcnow()+timedelta(hours=24))
    db.add(s);db.commit();db.refresh(s);return {"success":True,"id":s.id}

@router.get("/status")
def get_status(user=Depends(current_user),db:Session=Depends(get_db)):
    now=datetime.utcnow()
    rows=db.query(Status).filter(Status.expires_at>now).order_by(Status.created_at.desc()).all()
    result=[]
    for s in rows:
        owner=db.get(User,s.user_id)
        if owner:
            result.append({"id":s.id,"user_id":s.user_id,"user_name":owner.name,"avatar_url":owner.avatar_url,"text":s.text,"media_url":s.media_url,"background":s.background,"created_at":utc_iso(s.created_at),"viewed":db.query(StatusView).filter_by(status_id=s.id,viewer_id=user.id).first() is not None})
    return result

@router.post("/status/{status_id}/view")
def view_status(status_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    s=db.get(Status,status_id)
    if not s or s.expires_at<datetime.utcnow():raise HTTPException(404,"Status not found")
    if not db.query(StatusView).filter_by(status_id=status_id,viewer_id=user.id).first():
        db.add(StatusView(status_id=status_id,viewer_id=user.id));db.commit()
    return {"success":True}

@router.post("/upload")
async def upload(file:UploadFile=File(...),user=Depends(current_user)):
    return await save_upload(file)

@router.get("/health")
def health():return {"status":"ok","version":"3.0.0"}
