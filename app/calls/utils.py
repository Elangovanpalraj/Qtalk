from typing import Dict
from fastapi import WebSocket


class CallConnectionManager:
    """Manages active WebSockets for real-time WebRTC audio/video call signaling."""
    
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_signal(self, target_user_id: int, data: dict) -> bool:
        """Send WebRTC signal (SDP offer/answer/ICE candidate) to target user."""
        if target_user_id in self.active_connections:
            websocket = self.active_connections[target_user_id]
            await websocket.send_json(data)
            return True
        return False


call_manager = CallConnectionManager()
