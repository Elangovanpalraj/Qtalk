# Qtalk — upgraded WhatsApp-style local clone

This ZIP is an upgraded version of the Qtalk project you uploaded. It keeps the FastAPI + SQLAlchemy + SQLite + WebSocket architecture, but fixes the most important realtime/multi-user problems and adds more chat functionality.

## Main fixes in this build

### Realtime messaging
- WebSocket is authenticated with the JWT token instead of trusting a browser-supplied user ID.
- Messages can be sent through the WebSocket and are persisted on the server before broadcast.
- Every client send gets a `client_id` for idempotency. Retrying the same message does not create duplicates.
- The server broadcasts a saved message to the correct chat members only.
- Multiple browser tabs for the same user are supported.
- Offline messages are persisted and marked delivered when the recipient reconnects.
- Delivery receipts and read receipts are tracked per user.
- Message ordering uses database IDs and timestamps.
- WebSocket reconnect + heartbeat/ping is included.
- Presence is broadcast to members of chats.
- Typing events are checked against chat membership.

### Search
- Name search.
- Phone search.
- `9787609729`
- `+919787609729`
- `+91 9787609729`
- `97876-09729`
- Contacts are not required for phone search.
- Only limited public profile fields are returned.
- Search has a basic rate limit.

### Chat features
- 1-to-1 chats.
- Groups.
- Reply.
- Reactions.
- Edit your own message within 15 minutes.
- Delete your own message for everyone.
- Star messages.
- Pin messages.
- Search inside a chat.
- Clear chat for yourself.
- Archive chat.
- Mute chat.
- Block/unblock users.
- Group member add/remove API and group admin metadata.
- Image/audio/video/document upload.
- Profile photo and profile editing.
- Status with 24-hour expiry and view tracking.
- Dark mode.
- WebRTC voice/video call signaling for local/browser testing.

## Important: existing qtalk.db

This version adds new tables but does not intentionally delete your existing users/chats/messages.

If you already have `qtalk.db`, keep it.

The application runs `Base.metadata.create_all()` at startup, so the new tables are created automatically.

If you want a clean demo database, stop the server and delete `qtalk.db` once.

## Windows setup

Your earlier error:

```text
C:\Qtalk-Final>.venv\Scripts\activate
The system cannot find the path specified.
```

means the `.venv` folder does not exist in that project folder.

From PowerShell:

```powershell
cd C:\Qtalk-Final

py -m venv .venv

.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

If PowerShell blocks activation, you can skip activation and run:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Or simply run:

```powershell
run.bat
```

after creating the virtual environment and installing requirements.

## Two-user realtime test

1. Open normal Chrome.
2. Login as user A.
3. Open an Incognito window.
4. Open the same Qtalk URL.
5. Login as user B.
6. From user B search user A using either the name or phone number.
7. Open the chat.
8. Send several messages quickly from both sides.
9. Close one browser, send messages to that user, then reopen/reconnect.
10. Verify that the offline messages appear and unread count is correct.

Example phone searches:

```text
9787609729
+919787609729
+91 9787609729
97876-09729
```

## Browser cache

After replacing frontend files, use:

```text
Ctrl + F5
```

If an old tab is still connected, close it and open a fresh tab.

## What this is NOT

This is an independent Qtalk application. It is not WhatsApp's source code and it cannot connect to WhatsApp's private backend.

Do not advertise this local build as having WhatsApp's production security guarantees.

For public production deployment you still need:
- real SMS/OTP provider
- HTTPS
- PostgreSQL + migrations
- Redis/pub-sub for multi-server WebSocket fan-out
- object storage/CDN for media
- push notifications
- TURN infrastructure for reliable WebRTC
- abuse/rate limiting and moderation
- backups/monitoring
- privacy settings and legal compliance
- a properly designed end-to-end encryption/key-management system

## Feature roadmap

The current build focuses on fixing the message engine first. The next sensible production modules are:
1. media gallery + voice recording
2. full group management UI
3. status media/replies/privacy
4. notifications
5. stronger privacy settings
6. production call infrastructure
7. end-to-end encryption design
