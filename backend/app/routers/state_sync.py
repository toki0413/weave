from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UserState
from app.schemas import StatePayload
from app.routers.auth import get_current_user
from typing import Optional
import json
from pydantic import BaseModel
from typing import List, Dict, Any

router = APIRouter(prefix="/state", tags=["State Sync"])


class StateDiffPayload(BaseModel):
    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    modified: List[Dict[str, Any]] = []


@router.post("/")
async def save_state(payload: StatePayload, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """保存用户当前工作区状态（前后端同步）"""
    existing = db.query(UserState).filter(UserState.user_id == current_user.id).first()
    if existing:
        existing.nodes = payload.nodes
        existing.edges = payload.edges
        existing.node_id_counter = payload.node_id_counter
        existing.current_day = payload.current_day
        existing.day_snapshots = payload.day_snapshots
        existing.baseline_metrics = payload.baseline_metrics
        existing.welcome_dismissed = payload.welcome_dismissed
    else:
        state = UserState(
            user_id=current_user.id,
            nodes=payload.nodes,
            edges=payload.edges,
            node_id_counter=payload.node_id_counter,
            current_day=payload.current_day,
            day_snapshots=payload.day_snapshots,
            baseline_metrics=payload.baseline_metrics,
            welcome_dismissed=payload.welcome_dismissed,
        )
        db.add(state)
    db.commit()
    return {"status": "ok"}


@router.patch("/")
async def patch_state(payload: StateDiffPayload, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """增量 patch 更新用户工作区状态"""
    existing = db.query(UserState).filter(UserState.user_id == current_user.id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="No state found")

    # 处理 modified
    for item in payload.modified:
        field = item.get("field")
        value = item.get("value")
        if field and hasattr(existing, field):
            setattr(existing, field, value)

    # 处理 added（例如新增节点/边）
    for item in payload.added:
        target = item.get("target")
        value = item.get("value")
        if target == "nodes":
            existing.nodes = existing.nodes or []
            if value not in existing.nodes:
                existing.nodes.append(value)
        elif target == "edges":
            existing.edges = existing.edges or []
            if value not in existing.edges:
                existing.edges.append(value)

    # 处理 removed
    for item in payload.removed:
        target = item.get("target")
        value = item.get("value")
        if target == "nodes":
            existing.nodes = [n for n in (existing.nodes or []) if n.get("id") != value.get("id")]
        elif target == "edges":
            existing.edges = [e for e in (existing.edges or []) if not (
                e.get("from") == value.get("from") and e.get("to") == value.get("to") and e.get("type") == value.get("type")
            )]

    db.commit()
    return {"status": "ok", "patched": {"added": len(payload.added), "removed": len(payload.removed), "modified": len(payload.modified)}}


@router.get("/")
async def load_state(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """加载用户当前工作区状态"""
    state = db.query(UserState).filter(UserState.user_id == current_user.id).first()
    if not state:
        return JSONResponse(status_code=404, content={"detail": "No state found"})
    return {
        "nodes": state.nodes,
        "edges": state.edges,
        "node_id_counter": state.node_id_counter,
        "current_day": state.current_day,
        "day_snapshots": state.day_snapshots,
        "baseline_metrics": state.baseline_metrics,
        "welcome_dismissed": state.welcome_dismissed,
    }


@router.delete("/")
async def clear_state(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """清除用户工作区状态"""
    db.query(UserState).filter(UserState.user_id == current_user.id).delete()
    db.commit()
    return {"status": "ok"}
