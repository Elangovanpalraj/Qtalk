import json
from typing import Dict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket
        await self.broadcast_status()

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

    async def broadcast_status(self):
        online_users = list(self.active_connections.keys())
        payload = json.dumps({
            "type": "status_update",
            "online_users": online_users
        })
        for connection in self.active_connections.values():
            try:
                await connection.send_text(payload)
            except Exception:
                pass

    async def send_personal_message(self, message: str, username: str):
        if username in self.active_connections:
            await self.active_connections[username].send_text(message)

manager = ConnectionManager()

from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        # Maps user_id -> WebSocket connection
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, data: dict, receiver_id: int):
        if receiver_id in self.active_connections:
            await self.active_connections[receiver_id].send_text(json.dumps(data))

    async def broadcast_to_users(self, data: dict, user_ids: List[int]):
        for uid in user_ids:
            if uid in self.active_connections:
                await self.active_connections[uid].send_text(json.dumps(data))

manager = ConnectionManager()
