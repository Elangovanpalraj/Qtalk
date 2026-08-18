# Qtalk — realtime WhatsApp-style web chat

This build was reviewed against the supplied Qtalk project and the supplied WhatsApp reference screenshots. It keeps the existing FastAPI + SQLAlchemy + WebSocket structure and fixes the core two-user behaviour.

## Fixed in this build

### Realtime chat
- Sender sees their message on the **right**.
- Receiver sees the same message on the **left**.
- WebSocket broadcasts are serialized separately for each user, so `mine` is never shared between users.
- Message delivery is persisted before the event is sent.
- `✓` Sent → `✓✓` Delivered → `✓✓` blue Read.
- In a group, delivered/read ticks require all other members, matching WhatsApp-style semantics.
- Offline messages are marked delivered when the recipient reconnects.
- Read receipts are sent only to the original message sender(s).
- Duplicate sends are prevented with `client_id`.
- Mobile browser resume/network recovery reconnects the WebSocket.

### Presence
- Connecting users receive an initial online snapshot of users they share chats with.
- Online/offline transitions are broadcast only to relevant chat members.
- Multiple tabs/devices for the same account do not cause false offline transitions.
- Chat header changes between `online` and `last seen ...`.

### Login persistence
- Login creates both a 30-day JWT and an HttpOnly `qtalk_session` cookie.
- If localStorage is missing/stale, API requests fall back to the cookie.
- WebSocket authentication also falls back to the cookie.
- Normal refresh/navigation therefore does not require OTP again.

### Mobile
- User row opens the chat immediately.
- Chat becomes full-screen on mobile.
- Back button returns to the chat list.
- Existing desktop two-pane layout is preserved.

## Important Render deployment note

The default project database is SQLite. **Do not rely on an ephemeral Render filesystem for production data.** If Render restarts/redeploys and your SQLite file is not on persistent storage, users, chats, messages and sessions can disappear. For a real deployment, set `DATABASE_URL` to a persistent PostgreSQL database (recommended) or attach persistent storage for SQLite.

Example environment variable:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/qtalk
```

If you use PostgreSQL, add the PostgreSQL driver to `requirements.txt` before deploying.

## Windows

```cmd
cd /d D:\Qtalk
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

## Two-user test

Use exactly the setup you already use:

- System/Desktop = User A
- Mobile = User B

Test in this order:

1. Both users login once.
2. Both should show `online` while their WebSocket is connected.
3. A sends a message: A = right, B = left.
4. A should move from `✓` to `✓✓` when B's device receives it.
5. B opens the chat/read state: A should see blue `✓✓`.
6. Close B's browser/network, send A a message, then reconnect B.
7. The message should appear for B and A should receive the delivery update.
8. Refresh either browser. OTP login should not reappear while the session is valid.
