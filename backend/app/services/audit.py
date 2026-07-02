"""操作审计日志助手

医疗数据合规要求记录敏感数据访问行为。本模块提供轻量级 log_audit 函数，
各路由在关键操作点显式调用，避免侵入式中间件带来的性能开销。

记录字段：操作者、动作、资源类型/ID、目标用户、IP、UA、状态码、详情。
注意：details 字段不得包含明文敏感数据（密码、密文、密钥等）。
"""
import logging
from typing import Optional

from app.config import get_settings
from app.models import AuditLog

logger = logging.getLogger("cognitive_garden")


def log_audit(
    db,
    *,
    actor_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status_code: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """写入一条审计日志

    失败不抛异常，仅记日志——审计不应阻断业务流程。
    """
    settings = get_settings()
    if not settings.audit_log_enabled:
        return

    try:
        log = AuditLog(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            target_user_id=target_user_id,
            ip_address=ip_address,
            user_agent=(user_agent[:500] if user_agent else None),
            status_code=status_code,
            details=details,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        # 审计失败不能影响主流程，回滚后仅记日志
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("审计日志写入失败: %s", e)
