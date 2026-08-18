import asyncio
import json
from collections import defaultdict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.connections = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, ws: WebSocket):
        async with self._lock:
            self.connections[user_id].add(ws)

    def disconnect(self, user_id: int, ws: WebSocket):
        sockets = self.connections.get(user_id)
        if not sockets:
            return
        sockets.discard(ws)
        if not sockets:
            self.connections.pop(user_id, None)

    def online(self, user_id: int) -> bool:
        return bool(self.connections.get(user_id))

    async def send_user(self, user_id: int, payload: dict):
        sockets = list(self.connections.get(user_id, set()))
        if not sockets:
            return
        raw = json.dumps(payload, default=str)
        results = await asyncio.gather(
            *(self._send_one(user_id, ws, raw) for ws in sockets),
            return_exceptions=True,
        )
        for ws, result in zip(sockets, results):
            if result is not None:
                self.disconnect(user_id, ws)

    async def _send_one(self, user_id, ws, raw):
        try:
            await ws.send_text(raw)
            return None
        except Exception:
            return ws

    async def send_many(self, user_ids, payload: dict):
        ids = list(set(int(x) for x in user_ids))
        await asyncio.gather(*(self.send_user(uid, payload) for uid in ids), return_exceptions=True)


manager = ConnectionManager()
