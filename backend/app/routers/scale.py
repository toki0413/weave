"""认知量表路由：获取量表、提交答卷"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone

from app.database import get_db
from app.models import ScaleRecord, User
from app.routers.auth import get_current_user
from app.services.scales import SCALES, get_scale, list_scales, interpret, correlate_scale_with_graph
from app.services import key_manager
from app.services.crypto import encrypt_json, decrypt_json
from app.middleware.permission import filter_by_permission, require_permission
from app.services.sync_protocol import _get_device_sync, _increment_vector_clock
import asyncio

router = APIRouter(prefix="/scale", tags=["scale"])


def _require_key(user_id: str) -> bytes:
    """拿当前用户的加密密钥，没缓存就提示重新登录"""
    try:
        return key_manager.get_user_key(user_id)
    except RuntimeError:
        raise HTTPException(status_code=401, detail="加密密钥不可用，请重新登录")


# ========== 请求/响应模型 ==========
class AnswerItem(BaseModel):
    question_id: str
    score: int = Field(..., ge=0)


class ScaleSubmit(BaseModel):
    answers: List[AnswerItem]


class ScaleListItem(BaseModel):
    id: str
    name: str
    description: str
    total_score: int
    duration_min: int
    question_count: int


class ScaleDetail(BaseModel):
    id: str
    name: str
    description: str
    total_score: int
    duration_min: int
    questions: list


class ScaleResult(BaseModel):
    id: str
    scale_type: str
    total_score: int
    interpretation: str
    detail: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ========== 路由 ==========
@router.get("/", response_model=List[ScaleListItem])
def list_available_scales(
    current_user: User = Depends(get_current_user),
):
    """获取可用量表列表"""
    return list_scales()


@router.get("/{scale_id}", response_model=ScaleDetail)
def get_scale_detail(
    scale_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取量表详情（含所有问题）"""
    scale = get_scale(scale_id)
    if not scale:
        raise HTTPException(status_code=404, detail="量表不存在")
    return scale


@router.post("/{scale_id}/submit", response_model=ScaleResult)
def submit_scale(
    scale_id: str,
    data: ScaleSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交答卷，返回总分和解读"""
    scale = get_scale(scale_id)
    if not scale:
        raise HTTPException(status_code=404, detail="量表不存在")

    # 校验答题数量和分数范围
    question_map = {q["id"]: q for q in scale["questions"]}
    if len(data.answers) != len(question_map):
        raise HTTPException(
            status_code=400,
            detail=f"答题数量不匹配，应为 {len(question_map)} 题",
        )

    total = 0
    answer_list = []
    for ans in data.answers:
        q = question_map.get(ans.question_id)
        if not q:
            raise HTTPException(
                status_code=400,
                detail=f"未知题目: {ans.question_id}",
            )
        if ans.score < 0 or ans.score > q["max_score"]:
            raise HTTPException(
                status_code=400,
                detail=f"题目 {ans.question_id} 分数超出范围(0-{q['max_score']})",
            )
        total += ans.score
        answer_list.append({"question_id": ans.question_id, "score": ans.score})

    level, detail = interpret(scale_id, total)

    # 答案入库前加密
    key = _require_key(current_user.id)
    encrypted_answers = encrypt_json(answer_list, key)

    record = ScaleRecord(
        user_id=current_user.id,
        scale_type=scale_id,
        answers=encrypted_answers,
        total_score=total,
        interpretation=level,
        is_encrypted=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 更新 DeviceSync 向量时钟
    try:
        device_id = "default"
        sync = _get_device_sync(current_user.id, device_id, db)
        sync.vector_clock = _increment_vector_clock(sync.vector_clock, device_id)
        sync.last_sync_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        pass

    # 广播新量表事件到 SSE（家属端可订阅）
    try:
        broadcast_event({
            "type": "new_scale",
            "elderly_id": current_user.id,
            "data": {
                "scale_id": record.id,
                "scale_type": record.scale_type,
                "total_score": record.total_score,
                "interpretation": level
            }
        })
    except Exception:
        pass

    return ScaleResult(
        id=record.id,
        scale_type=record.scale_type,
        total_score=record.total_score,
        interpretation=level,
        detail=detail,
        created_at=record.created_at,
    )


@router.get("/history/all", response_model=List[ScaleResult])
def list_scale_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scale_type: Optional[str] = None,
    limit: int = 50,
):
    """查询当前用户的量表评估历史"""
    query = db.query(ScaleRecord)
    query = filter_by_permission(query, current_user, db)
    if scale_type:
        query = query.filter(ScaleRecord.scale_type == scale_type)
    records = query.order_by(ScaleRecord.created_at.desc()).limit(limit).all()

    results = []
    for r in records:
        level, detail = interpret(r.scale_type, r.total_score)
        results.append(ScaleResult(
            id=r.id,
            scale_type=r.scale_type,
            total_score=r.total_score,
            interpretation=level,
            detail=detail,
            created_at=r.created_at,
        ))
    return results


@router.get("/last-assessment/{scale_id}")
def get_last_assessment(
    scale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某量表上次评估时间，用于判断是否到期需要复评"""
    record = db.query(ScaleRecord).filter(
        ScaleRecord.user_id == current_user.id,
        ScaleRecord.scale_type == scale_id,
    ).order_by(ScaleRecord.created_at.desc()).first()

    if not record:
        return {"has_history": False, "last_date": None, "days_since": None, "due": True}

    days_since = (datetime.now(timezone.utc) - record.created_at).days
    # 建议每90天复评一次
    due = days_since >= 90
    return {
        "has_history": True,
        "last_date": record.created_at.isoformat(),
        "last_score": record.total_score,
        "days_since": days_since,
        "due": due,
        "recommended_interval_days": 90,
    }


@router.post("/{scale_id}/correlate")
def correlate_with_graph(
    scale_id: str,
    graph_metrics: dict,
    current_user: User = Depends(get_current_user),
):
    """
    量表分数与图谱指标的关联分析。
    需要前端传入最近的图谱指标，后端返回关联分析结果。
    """
    scale = get_scale(scale_id)
    if not scale:
        raise HTTPException(status_code=404, detail="量表不存在")

    # 从请求体获取量表分数（前端传入最近一次评估的分数）
    scale_score = graph_metrics.get("scale_score", 0)
    metrics = graph_metrics.get("metrics", {})

    findings = correlate_scale_with_graph(scale_id, scale_score, metrics)
    return {"scale_type": scale_id, "scale_score": scale_score, "findings": findings}
