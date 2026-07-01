"""训练游戏记录路由：提交分数 / 获取历史"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app.models import TrainingRecord, User
from app.schemas import TrainingRecordCreate, TrainingRecordOut
from app.routers.auth import get_current_user

router = APIRouter(prefix="/training", tags=["training"])


@router.post("/", response_model=TrainingRecordOut)
def submit_training(
    data: TrainingRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交一次训练游戏的分数"""
    record = TrainingRecord(
        user_id=current_user.id,
        game_type=data.game_type,
        score=data.score,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/", response_model=List[TrainingRecordOut])
def list_training(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 50,
):
    """获取当前用户的训练历史，按时间倒序"""
    records = (
        db.query(TrainingRecord)
        .filter(TrainingRecord.user_id == current_user.id)
        .order_by(TrainingRecord.completed_at.desc())
        .limit(limit)
        .all()
    )
    return records


@router.get("/stats")
def training_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
):
    """获取训练统计（按游戏类型聚合）"""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = (
        db.query(TrainingRecord)
        .filter(
            TrainingRecord.user_id == current_user.id,
            TrainingRecord.completed_at >= cutoff,
        )
        .all()
    )

    stats = {}
    for r in records:
        gt = r.game_type
        if gt not in stats:
            stats[gt] = {"count": 0, "total_score": 0, "best_score": 0}
        stats[gt]["count"] += 1
        stats[gt]["total_score"] += r.score
        if r.score > stats[gt]["best_score"]:
            stats[gt]["best_score"] = r.score

    for gt in stats:
        stats[gt]["avg_score"] = round(stats[gt]["total_score"] / stats[gt]["count"], 1)

    return {"stats": stats, "total_sessions": len(records)}
