import json
import logging
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # active_connections maps user_id (int) -> WebSocket connection
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        """
        புதிய பயனரின் WebSocket இணைப்பை ஏற்கிறது.
        """
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"User {user_id} connected. Total active connections: {len(self.active_connections)}")
        
        # பயனர் ஆன்லைனுக்கு வந்ததை மற்ற அனைவருக்கும் தெரிவிக்க
        await self.broadcast_online_status(user_id, is_online=True)

    def disconnect(self, user_id: int):
        """
        பயனரின் இணைப்பைத் துண்டிக்கிறது.
        """
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected.")

    def is_user_online(self, user_id: int) -> bool:
        """
        குறிப்பிட்ட பயனர் ஆன்லைனில் இருக்கிறாரா என சரிபார்க்கிறது.
        """
        return user_id in self.active_connections

    def get_online_users(self) -> List[int]:
        """
        தற்போது ஆன்லைனில் உள்ள அனைத்து பயனர்களின் ID பட்டியலைத் தருகிறது.
        """
        return list(self.active_connections.keys())

    async def send_personal_message(self, data: dict, receiver_id: int) -> bool:
        """
        ஒரு குறிப்பிட்ட பயனருக்கு மட்டும் மெசேஜ் அனுப்பும் (Direct Chat).
        """
        if receiver_id in self.active_connections:
            websocket = self.active_connections[receiver_id]
            try:
                await websocket.send_text(json.dumps(data))
                return True  # Delivered
            except Exception as e:
                logger.error(f"Error sending message to user {receiver_id}: {e}")
                self.disconnect(receiver_id)
        return False  # User is offline

    async def broadcast_to_users(self, data: dict, user_ids: List[int], exclude_sender_id: Optional[int] = None):
        """
        குரூப்பில் உள்ள பல பயனர்களுக்கு ஒரே நேரத்தில் மெசேஜ் அனுப்பும் (Group Chat).
        """
        payload = json.dumps(data)
        for uid in user_ids:
            if uid == exclude_sender_id:
                continue  # மெசேஜ் அனுப்பியவருக்கு மீண்டும் அனுப்ப தேவையில்லை
            
            if uid in self.active_connections:
                try:
                    await self.active_connections[uid].send_text(payload)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {uid}: {e}")
                    self.disconnect(uid)

    async def broadcast_online_status(self, user_id: int, is_online: bool):
        """
        ஒரு பயனர் Online/Offline வரும்போது மற்ற எல்லா ஆன்லைன் பயனர்களுக்கும் அறிவிக்கும்.
        """
        payload = json.dumps({
            "type": "user_status",
            "user_id": user_id,
            "status": "online" if is_online else "offline",
            "online_users": self.get_online_users()
        })
        
        for uid, connection in list(self.active_connections.items()):
            if uid != user_id:
                try:
                    await connection.send_text(payload)
                except Exception:
                    self.disconnect(uid)

    async def send_typing_indicator(self, sender_id: int, receiver_id: int, is_typing: bool):
        """
        வாட்ஸ்அப்பில் "Typing..." எனக் காட்டுவதற்கான செயல்பாடு.
        """
        payload = {
            "type": "typing",
            "sender_id": sender_id,
            "is_typing": is_typing
        }
        await self.send_personal_message(payload, receiver_id)


# Singleton Instance
manager = ConnectionManager()
