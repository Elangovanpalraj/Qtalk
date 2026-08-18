from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import APP_NAME, UPLOAD_DIR
from app.database import Base, engine, SessionLocal
from app.models import User, Chat, Message, MessageDelivery
from app.auth import router as auth_router
from app.api import router as api_router, create_message_record, MessageIn, chat_member_ids, msg_json
from app.security import get_user_id
from app.realtime import manager

Base.metadata.create_all(bind=engine)

app = FastAPI(title=APP_NAME, version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")


def iso_now():
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


async def broadcast_presence(db: Session, user_id: int, online: bool):
    """Notify only users who actually share a chat with this user."""
    chats = db.query(Chat).all()
    targets = set()
    for chat in chats:
        ids = chat_member_ids(chat)
        if user_id in ids:
            targets.update(ids)
    targets.discard(user_id)
    await manager.send_many(
        targets,
        {
            "type": "presence",
            "user_id": user_id,
            "online": online,
            "last_seen": iso_now(),
        },
    )


def mark_pending_delivered(db: Session, user_id: int):
    """Mark stored messages as delivered when the recipient reconnects."""
    chats = db.query(Chat).all()
    changed = []
    now = datetime.utcnow()
    for chat in chats:
        if user_id not in chat_member_ids(chat):
            continue
        rows = (
            db.query(Message)
            .filter(
                Message.chat_id == chat.id,
                Message.sender_id != user_id,
                Message.deleted_at == None,
            )
            .order_by(Message.id.desc())
            .limit(1000)
            .all()
        )
        for message in rows:
            exists = (
                db.query(MessageDelivery)
                .filter_by(message_id=message.id, user_id=user_id)
                .first()
            )
            if not exists:
                db.add(
                    MessageDelivery(
                        message_id=message.id,
                        user_id=user_id,
                        delivered_at=now,
                    )
                )
                message.delivered_at = message.delivered_at or now
                changed.append((message.id, chat.id, message.sender_id))
    db.commit()
    return changed


@app.websocket("/ws")
async def websocket(ws: WebSocket):
    user_id = None
    db: Session | None = None
    try:
        await ws.accept()

        # The browser may send its cached JWT, but the HttpOnly cookie is the
        # fallback. This keeps realtime alive after localStorage is cleared.
        hello = await ws.receive_json()
        token = hello.get("token") or ws.cookies.get("qtalk_session")
        if not token:
            await ws.close(code=1008)
            return

        try:
            user_id = get_user_id(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            )
        except Exception:
            await ws.close(code=1008)
            return

        db = SessionLocal()
        user = db.get(User, user_id)
        if not user:
            await ws.close(code=1008)
            return

        was_online = manager.online(user_id)
        await manager.connect(user_id, ws)
        user.is_online = True
        user.last_seen = datetime.utcnow()
        db.commit()

        # Only broadcast a new online transition. Multiple tabs/devices for the
        # same account must not make the contact flicker offline/online.
        if not was_online:
            await broadcast_presence(db, user_id, True)

        # Tell this newly connected account which of its chat contacts are
        # already online. A snapshot avoids waiting for another presence event.
        visible_ids = set()
        for chat in db.query(Chat).all():
            ids = chat_member_ids(chat)
            if user_id in ids:
                visible_ids.update(ids)
        visible_ids.discard(user_id)
        for other_id in visible_ids:
            if manager.online(other_id):
                await manager.send_user(
                    user_id,
                    {
                        "type": "presence",
                        "user_id": other_id,
                        "online": True,
                        "last_seen": iso_now(),
                    },
                )

        # Offline messages become delivered as soon as this account reconnects.
        delivery_changes = mark_pending_delivered(db, user_id)
        grouped = {}
        for message_id, chat_id, sender_id in delivery_changes:
            grouped.setdefault((sender_id, chat_id), []).append(message_id)
        for (sender_id, chat_id), message_ids in grouped.items():
            await manager.send_user(
                sender_id,
                {
                    "type": "delivery",
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "message_ids": message_ids,
                },
            )

        await ws.send_json({"type": "ready", "user_id": user_id})

        while True:
            data = await ws.receive_json()
            kind = data.get("type")

            if kind == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if kind == "typing":
                try:
                    target = int(data["to_user_id"])
                    chat_id = int(data.get("chat_id") or 0)
                except Exception:
                    continue
                chat = db.get(Chat, chat_id)
                if chat and user_id in chat_member_ids(chat) and target in chat_member_ids(chat):
                    await manager.send_user(
                        target,
                        {
                            "type": "typing",
                            "from_user_id": user_id,
                            "chat_id": chat.id,
                            "is_typing": bool(data.get("is_typing")),
                        },
                    )
                continue

            if kind == "message":
                try:
                    chat_id = int(data["chat_id"])
                except Exception:
                    await ws.send_json({"type": "message_error", "message": "Invalid chat"})
                    continue

                client_id = data.get("client_id")
                msg_data = MessageIn(
                    chat_id=chat_id,
                    text=data.get("text"),
                    reply_to_id=data.get("reply_to_id"),
                    client_id=client_id,
                )
                try:
                    chat, message, duplicate = create_message_record(db, user_id, msg_data)
                    members = chat_member_ids(chat)

                    if not duplicate:
                        # Serialize separately for every client so `mine` is
                        # always relative to the receiving account.
                        for recipient_id in members:
                            await manager.send_user(
                                recipient_id,
                                {
                                    "type": "message",
                                    "message": msg_json(db, message, recipient_id),
                                },
                            )

                        # Tell the sender immediately that the connected
                        # recipient's device received the message.
                        for recipient_id in members:
                            if recipient_id != user_id and manager.online(recipient_id):
                                await manager.send_user(
                                    user_id,
                                    {
                                        "type": "delivery",
                                        "chat_id": chat.id,
                                        "user_id": recipient_id,
                                        "message_ids": [message.id],
                                    },
                                )

                    # Ack only the sending browser/tab. The broadcast above is
                    # the actual message event; this ack is for client_id state.
                    await manager.send_user(
                        user_id,
                        {
                            "type": "message_ack",
                            "client_id": client_id,
                            "message": msg_json(db, message, user_id),
                        },
                    )
                except Exception as exc:
                    db.rollback()
                    await manager.send_user(
                        user_id,
                        {
                            "type": "message_error",
                            "client_id": client_id,
                            "message": str(exc),
                        },
                    )
                continue

            if kind == "call":
                try:
                    target = int(data["to_user_id"])
                except Exception:
                    continue
                if manager.online(target):
                    await manager.send_user(target, {**data, "from_user_id": user_id})
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if user_id is not None:
            was_last_connection = len(manager.connections.get(user_id, set())) <= 1
            manager.disconnect(user_id, ws)
            if db is None:
                db = SessionLocal()
            user = db.get(User, user_id)
            if user and was_last_connection and not manager.online(user_id):
                user.is_online = False
                user.last_seen = datetime.utcnow()
                db.commit()
                await broadcast_presence(db, user_id, False)
            if db:
                db.close()
