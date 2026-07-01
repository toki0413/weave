"""家属同步路由：SSE 实时推送老人新会话/量表事件"""
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User, FamilyLink, Session as DBSession, ScaleRecord
from app.routers.auth import get_current_user

router = APIRouter(prefix="/events", tags=["family-sync"])


@router.get("/family/{elderly_id}")
async def family_events(
    elderly_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE 端点：家属订阅指定老人的新会话/量表事件"""
    # 验证关系
    link = (
        db.query(FamilyLink)
        .filter(
            FamilyLink.elderly_user_id == elderly_id,
            FamilyLink.family_user_id == current_user.id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="未绑定该老人")

    q = asyncio.Queue(maxsize=100)
    # 复用 main.py 中的全局事件队列，但需要按 elderly_id 过滤
    # 这里为简化实现，使用一个独立的家庭事件队列注册器
    from app.main import _event_queues
    _event_queues.append(q)

    async def event_generator():
        try:
            while True:
                msg = await q.get()
                data = json.loads(msg)
                # 只转发与该老人相关的事件
                if data.get("elderly_id") == elderly_id:
                    yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            try:
                _event_queues.remove(q)
            except ValueError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")
