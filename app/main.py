from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
import json
import os
import shutil
from datetime import datetime

app = FastAPI()

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            receiver TEXT,
            message TEXT,
            file_url TEXT,
            timestamp TEXT,
            is_read INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket
        await self.broadcast_status()

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

    async def send_personal_message(self, data: dict, receiver: str):
        if receiver in self.active_connections:
            await self.active_connections[receiver].send_text(json.dumps(data))

    async def broadcast_status(self):
        online_users = list(self.active_connections.keys())
        data = {"type": "status_update", "online_users": online_users}
        for ws in self.active_connections.values():
            await ws.send_text(json.dumps(data))

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/messages/{user1}/{user2}")
async def get_messages(user1: str, user2: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE messages SET is_read=1 WHERE sender=? AND receiver=?", (user2, user1))
    conn.commit()
    
    cursor.execute('''
        SELECT id, sender, receiver, message, file_url, timestamp, is_read FROM messages 
        WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) 
        ORDER BY id ASC
    ''', (user1, user2, user2, user1))
    rows = cursor.fetchall()
    conn.close()
    
    messages = [
        {"id": r[0], "sender": r[1], "receiver": r[2], "message": r[3], "file_url": r[4], "timestamp": r[5], "is_read": r[6]} 
        for r in rows
    ]
    return JSONResponse(content=messages)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = file.filename.split('.')[-1]
    filename = f"{datetime.now().timestamp()}.{ext}"
    file_location = f"{UPLOAD_DIR}/{filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"file_url": f"/{file_location}"}

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            msg_type = message_data.get("type", "message")
            
            if msg_type == "typing":
                message_data['sender'] = username
                await manager.send_personal_message(message_data, message_data['receiver'])
                continue
            if msg_type == "read_ack":
                conn = sqlite3.connect("database.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE messages SET is_read=1 WHERE sender=? AND receiver=?", (message_data['sender'], username))
                conn.commit()
                conn.close()
                await manager.send_personal_message({"type": "read_ack", "by": username}, message_data['sender'])
                continue
            if msg_type == "delete_msg":
                msg_id = message_data.get("msg_id")
                conn = sqlite3.connect("database.db")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM messages WHERE id=?", (msg_id,))
                conn.commit()
                conn.close()
                payload = {"type": "delete_msg", "msg_id": msg_id}
                await manager.send_personal_message(payload, message_data['receiver'])
                await manager.send_personal_message(payload, username)
                continue
                
            # Standard Message & Voice Note Handling
            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (sender, receiver, message, file_url, timestamp, is_read) VALUES (?, ?, ?, ?, ?, 0)",
                (username, message_data['receiver'], message_data.get('message', ''), message_data.get('file_url', ''), datetime.now().strftime("%I:%M %p"))
            )
            msg_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            message_data['type'] = "message"
            message_data['id'] = msg_id
            message_data['sender'] = username
            message_data['timestamp'] = datetime.now().strftime("%I:%M %p")
            message_data['is_read'] = 0
            
            await manager.send_personal_message(message_data, message_data['receiver'])
            await manager.send_personal_message(message_data, username)
            
    except WebSocketDisconnect:
        manager.disconnect(username)
        await manager.broadcast_status()
