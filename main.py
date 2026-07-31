import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

# Serve static files
os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.messages_db: List[dict] = []
        self.registered_users: Set[str] = {"Rahul", "Priya", "Kumar", "Alex", "Nexus AI"}
        self.groups: Dict[str, dict] = {
            "Developers Hub": {"admin": "System", "members": []},
            "Tech Squad": {"admin": "System", "members": []}
        }
        self.msg_id_counter = 1

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket
        self.registered_users.add(username)
        await self.broadcast_status()

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

    async def broadcast_status(self):
        online_users = list(self.active_connections.keys())
        status_event = json.dumps({
            "type": "status_update",
            "online_users": online_users,
            "all_users": list(self.registered_users)
        })
        for ws in self.active_connections.values():
            await ws.send_text(status_event)

    async def send_personal_message(self, message: str, username: str):
        if username in self.active_connections:
            await self.active_connections[username].send_text(message)

    async def broadcast_to_group(self, group_name: str, message: str):
        for username, ws in self.active_connections.items():
            await ws.send_text(message)

manager = ConnectionManager()

async def generate_ai_reply(prompt: str) -> str:
    await asyncio.sleep(1)
    prompt_lower = prompt.lower()
    
    if "code" in prompt_lower or "python" in prompt_lower or "data analysis" in prompt_lower:
        return (
            "🤖 **Nexus AI**:\n\nHere is a quick Python snippet for Data Analysis using Pandas:\n\n"
            "```python\n"
            "import pandas as pd\n"
            "import numpy as np\n\n"
            "# Sample Data Analytics DataFrame\n"
            "df = pd.DataFrame({\n"
            "    'Category': ['A', 'B', 'A', 'C', 'B'],\n"
            "    'Values': [10, 20, 15, 30, 25]\n"
            "})\n\n"
            "print(df.groupby('Category').mean())\n"
            "```"
        )
    elif "tamil" in prompt_lower or "ennadhu" in prompt_lower or "sappitiya" in prompt_lower or "hi" in prompt_lower or "bro" in prompt_lower:
        return "🤖 **Nexus AI**: வணக்கங்கள்! நான் Nexus AI. உங்களுக்கு என்ன உதவி வேண்டும்?"
    else:
        return f"🤖 **Nexus AI**:\n\nI processed your request: *'{prompt}'*\n\nHow else can I assist you with code or project development today?"

@app.get("/")
async def get_index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# Keep-Alive Health Endpoint to prevent Render Sleep Delay
@app.get("/health")
async def health_check():
    return {"status": "active"}

@app.get("/users")
async def get_users():
    return JSONResponse(content={"users": list(manager.registered_users)})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join("uploads", file.filename)
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    return {"file_url": f"/uploads/{file.filename}", "filename": file.filename, "size": len(content)}

@app.get("/messages/{user1}/{user2}")
async def get_messages(user1: str, user2: str):
    relevant = [
        m for m in manager.messages_db
        if (m["sender"] == user1 and m["receiver"] == user2) or
           (m["sender"] == user2 and m["receiver"] == user1) or
           (m["receiver"] == user2)
    ]
    return relevant

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(username, websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            msg_type = data.get("type")

            if msg_type == "message":
                msg_id = manager.msg_id_counter
                manager.msg_id_counter += 1
                
                timestamp = datetime.now().strftime("%I:%M %p")
                msg_obj = {
                    "id": msg_id,
                    "sender": username,
                    "receiver": data["receiver"],
                    "message": data.get("message", ""),
                    "file_url": data.get("file_url", ""),
                    "filename": data.get("filename", ""),
                    "reply_to": data.get("reply_to"),
                    "timestamp": timestamp,
                    "is_read": False,
                    "read_at": None
                }
                manager.messages_db.append(msg_obj)

                payload = json.dumps({"type": "message", **msg_obj})
                if data["receiver"] in manager.groups:
                    await manager.broadcast_to_group(data["receiver"], payload)
                else:
                    await manager.send_personal_message(payload, data["receiver"])
                    await manager.send_personal_message(payload, username)

                user_msg = data.get("message", "").strip()
                if user_msg.startswith("@ai") or data["receiver"] == "Nexus AI":
                    ai_prompt = user_msg.replace("@ai", "").strip()
                    ai_reply = await generate_ai_reply(ai_prompt)
                    
                    ai_msg_obj = {
                        "id": manager.msg_id_counter,
                        "sender": "Nexus AI",
                        "receiver": username,
                        "message": ai_reply,
                        "file_url": "",
                        "timestamp": datetime.now().strftime("%I:%M %p"),
                        "is_read": True
                    }
                    manager.msg_id_counter += 1
                    manager.messages_db.append(ai_msg_obj)
                    await manager.send_personal_message(json.dumps({"type": "message", **ai_msg_obj}), username)

            elif msg_type == "read_ack":
                sender = data.get("sender")
                now_str = datetime.now().strftime("%I:%M %p")
                for m in manager.messages_db:
                    if m["sender"] == sender and m["receiver"] == username and not m["is_read"]:
                        m["is_read"] = True
                        m["read_at"] = now_str
                
                await manager.send_personal_message(json.dumps({
                    "type": "read_ack",
                    "sender": username,
                    "read_at": now_str
                }), sender)

            elif msg_type == "typing":
                await manager.send_personal_message(json.dumps({
                    "type": "typing",
                    "sender": username,
                    "is_typing": data.get("is_typing", False)
                }), data["receiver"])

            elif msg_type in ["reaction", "delete_msg", "call_offer", "call_answer", "ice_candidate", "end_call"]:
                await manager.send_personal_message(data_str, data["receiver"])

    except WebSocketDisconnect:
        manager.disconnect(username)
        await manager.broadcast_status()