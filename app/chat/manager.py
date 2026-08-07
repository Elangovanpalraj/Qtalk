import json
import logging
from typing import Dict, List, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections, direct messaging, group broadcasts,
    typing indicators, and real-time online/offline user status updates.
    """

    def __init__(self):
        # Maps user_id (int) -> WebSocket connection instance
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        """
        Accepts and stores a new user's WebSocket connection, then broadcasts online status.
        """
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"User {user_id} connected. Active connections: {len(self.active_connections)}")

        # Broadcast to everyone that this user is now ONLINE
        await self.broadcast_online_status(user_id, is_online=True)

    async def disconnect(self, user_id: int):
        """
        Removes user connection and notifies everyone that user went OFFLINE.
        """
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected.")

            # Broadcast to everyone that this user is now OFFLINE
            await self.broadcast_online_status(user_id, is_online=False)

    def is_user_online(self, user_id: int) -> bool:
        """
        Checks if a specific user is currently connected.
        """
        return user_id in self.active_connections

    def get_online_users(self) -> List[int]:
        """
        Returns a list of all currently online user IDs.
        """
        return list(self.active_connections.keys())

    async def send_personal_message(self, data: dict, receiver_id: int) -> bool:
        """
        Sends a real-time JSON message directly to a target user (1-on-1 Chat).
        """
        if receiver_id in self.active_connections:
            websocket = self.active_connections[receiver_id]
            try:
                await websocket.send_text(json.dumps(data))
                return True  # Successfully delivered
            except Exception as e:
                logger.error(f"Error sending message to user {receiver_id}: {e}")
                await self.disconnect(receiver_id)
        return False  # User is offline

    async def broadcast_to_users(self, data: dict, user_ids: List[int], exclude_sender_id: Optional[int] = None):
        """
        Broadcasts message to multiple users in a group, excluding the sender if specified.
        """
        payload = json.dumps(data)
        for uid in user_ids:
            if uid == exclude_sender_id:
                continue  # Skip sending back to the sender

            if uid in self.active_connections:
                try:
                    await self.active_connections[uid].send_text(payload)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {uid}: {e}")
                    await self.disconnect(uid)

    async def broadcast_online_status(self, user_id: int, is_online: bool):
        """
        Notifies all connected clients when a user comes online or goes offline.
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
                    await self.disconnect(uid)

    async def send_typing_indicator(self, sender_id: int, receiver_id: int, is_typing: bool):
        """
        Sends real-time 'Typing...' indicator events to the target receiver.
        """
        payload = {
            "type": "typing",
            "sender_id": sender_id,
            "is_typing": is_typing
        }
        await self.send_personal_message(payload, receiver_id)


# Singleton Instance to be imported across app
manager = ConnectionManager()
