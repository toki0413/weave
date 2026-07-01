"""同步协议路由：离线设备的 pull / push 入口"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.services.sync_protocol import pull_changes, push_changes, resolve_conflict
from app.middleware.permission import filter_by_permission, require_permission

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/pull")
def sync_pull(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拉取服务器上自上次同步以来的变更

    请求体: { device_id, last_vector_clock }
    """
    user_id = current_user.id
    device_id = data.get("device_id", "default")
    last_vector_clock = data.get("last_vector_clock")
    return pull_changes(user_id, device_id, last_vector_clock, db)


@router.post("/push")
def sync_push(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """推送客户端变更到服务器

    请求体: { device_id, changes }
    """
    user_id = current_user.id
    device_id = data.get("device_id", "default")
    changes = data.get("changes", {})
    return push_changes(user_id, device_id, changes, db)


@router.post("/resolve")
def sync_resolve(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """显式冲突解决（前端调用以确认冲突处理结果）"""
    local = payload.get("local_data", {})
    server = payload.get("server_data", {})
    rule = payload.get("rule", "lww")
    return resolve_conflict(local, server, rule)
