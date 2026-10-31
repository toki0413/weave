"""记忆衰退分析路由：对比近期叙事，输出衰退分数与时间线"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.services.decline import analyze_narrative_diff, build_entity_timeline
from app.middleware.permission import resolve_target_user

router = APIRouter(prefix="/decline", tags=["decline"])


@router.get("/analysis")
def get_decline_analysis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    window_days: int = Query(7, ge=1, le=90, description="对比窗口天数"),
    elderly_id: Optional[str] = Query(None, description="分析对象；家属/医生未传时默认首个绑定对象"),
):
    """获取指定老人的记忆衰退分析结果（带权限校验）"""
    target = resolve_target_user(db, current_user, elderly_id)
    return analyze_narrative_diff(target, db, window_days=window_days)


@router.get("/timeline")
def get_decline_timeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = Query(30, ge=1, le=180, description="时间线覆盖天数"),
    elderly_id: Optional[str] = Query(None, description="同 /analysis，分析对象"),
):
    """获取实体出现频率时间线，标注正在消失的实体（带权限校验）"""
    target = resolve_target_user(db, current_user, elderly_id)
    return build_entity_timeline(target, db, days=days)
