"""本周记忆卡片：家属端聚合生成 + 公开链接读取（K 因子增长回路）

隐私红线：卡片 payload 只含计数、高频实体、趋势等级等聚合信息，
绝不包含叙事原文、量表分数、告警内容。公开端点按 id 免登录读取。
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FamilyLink, MemoryCardShare, Session as DBSession
from app.routers.auth import get_current_user
from app.routers.session import rate_limit

logger = logging.getLogger("cognitive_garden")

router = APIRouter(prefix="/card", tags=["memory-card"])

_MAX_TOP_ENTITIES = 5


def _build_payload(db: Session, elderly_user_id: str, elderly_name: str,
                   days: int) -> dict:
    """聚合窗口内的脱敏卡片数据"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sessions = (
        db.query(DBSession)
        .filter(DBSession.user_id == elderly_user_id, DBSession.created_at >= since)
        .order_by(DBSession.created_at.desc())
        .all()
    )

    record_count = len(sessions)
    total_chars = sum(len(s.narrative or "") for s in sessions)
    active_days = len({
        (s.created_at or since).astimezone(timezone.utc).date() for s in sessions
    })

    # 高频实体：取最近一次会话的 graph 节点，按权重排序，排除 self
    top_entities = []
    if sessions and sessions[0].graph:
        nodes = (sessions[0].graph or {}).get("nodes") or []
        scored = []
        for n in nodes:
            if not isinstance(n, dict) or n.get("type") == "self":
                continue
            label = n.get("label") or n.get("name") or n.get("id") or ""
            if not label:
                continue
            weight = n.get("weight") or n.get("count") or 1
            scored.append((label, n.get("type", ""), weight))
        scored.sort(key=lambda x: x[2], reverse=True)
        top_entities = [
            {"label": label, "type": kind} for label, kind, _ in scored[:_MAX_TOP_ENTITIES]
        ]

    # 认知趋势：只透出等级文案，不透出分数（公开端脱敏）
    trend_level = "暂无数据"
    if sessions:
        latest_metrics = sessions[0].metrics or {}
        health = sessions[0].health_score
        if health is not None:
            trend_level = "状态稳定" if health >= 70 else "建议关注"

    week_start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return {
        "elderly_name": elderly_name or "家人",
        "week_label": f"近{days}天",
        "week_start": week_start,
        "record_count": record_count,
        "total_chars": total_chars,
        "active_days": active_days,
        "top_entities": top_entities,
        "trend_level": trend_level,
    }


@router.post("/generate")
def generate_memory_card(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """家属生成本周记忆卡片，返回卡片 id（拼公开链接 /#/share/card/{id}）"""
    if (current_user.role or "") != "family":
        raise HTTPException(status_code=403, detail="仅家属角色可生成记忆卡片")
    days = max(1, min(days, 30))

    link = (
        db.query(FamilyLink)
        .filter(FamilyLink.family_user_id == current_user.id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="尚未绑定老人")

    from app.models import User
    elderly = db.query(User).filter(User.id == link.elderly_user_id).first()
    if elderly is None:
        raise HTTPException(status_code=404, detail="绑定的老人不存在")

    payload = _build_payload(db, elderly.id, elderly.name, days)
    card = MemoryCardShare(
        family_user_id=current_user.id,
        elderly_user_id=elderly.id,
        week_start=datetime.now(timezone.utc) - timedelta(days=days),
        days=days,
        payload=payload,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return {"id": card.id, "payload": payload}


@router.get("/latest")
def latest_memory_card(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """家属端读取最近生成的卡片（30 天内）"""
    if (current_user.role or "") != "family":
        raise HTTPException(status_code=403, detail="仅家属角色可查看记忆卡片")
    since = datetime.now(timezone.utc) - timedelta(days=30)
    card = (
        db.query(MemoryCardShare)
        .filter(MemoryCardShare.family_user_id == current_user.id,
                MemoryCardShare.created_at >= since)
        .order_by(MemoryCardShare.created_at.desc())
        .first()
    )
    if not card:
        return {"card": None}
    return {"card": {"id": card.id, "payload": card.payload,
                     "created_at": card.created_at}}


@router.get("/public/{card_id}", dependencies=[rate_limit(30, 60)])
def read_public_card(
    card_id: str,
    db: Session = Depends(get_db),
):
    """公开读取卡片（免登录）：访客落地页数据源。限频 30 次/分钟。"""
    card = db.query(MemoryCardShare).filter(MemoryCardShare.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在或已失效")
    return {"payload": card.payload}
