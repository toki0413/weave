"""WebSocket 连接管理器：按 user_id 分组管理所有活跃连接"""
import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("cognitive_garden")


class ConnectionManager:
    """管理 WebSocket 连接：{user_id: [websocket, ...]}"""

    def __init__(self):
        # user_id -> list of websocket connections
        self._connections: Dict[str, List[WebSocket]] = {}
        # websocket -> user_id 映射，用于快速断开查找
        self._ws_to_user: Dict[WebSocket, str] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        self._ws_to_user[websocket] = user_id
        logger.info("WebSocket connected: user=%s total_conns=%d", user_id, len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self._connections:
            try:
                self._connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[user_id]:
                del self._connections[user_id]
        self._ws_to_user.pop(websocket, None)
        logger.info("WebSocket disconnected: user=%s", user_id)

    async def send_to_user(self, user_id: str, message: dict):
        """发送给指定用户的所有设备"""
        if user_id not in self._connections:
            return
        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_to_role(self, role: str, message: dict):
        """发送给某角色的所有在线用户（需外部传入角色列表）"""
        # 本函数需要外部知道 user_id -> role 映射；
        # 此处简单广播给所有连接，实际调用方应过滤。
        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for user_id, ws_list in self._connections.items():
            for ws in ws_list:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append((user_id, ws))
        for user_id, ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_to_users(self, user_ids: List[str], message: dict):
        """发送给指定用户列表"""
        for uid in user_ids:
            await self.send_to_user(uid, message)

    def get_user_connections(self, user_id: str) -> List[WebSocket]:
        return list(self._connections.get(user_id, []))


# 全局单例
manager = ConnectionManager()
