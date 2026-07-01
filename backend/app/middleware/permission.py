"""权限过滤中间件：按角色控制数据可见范围

规则：
- elderly：只能看到自己的数据（user_id == current_user.id）
- family：能看到绑定的老人的数据（user_id in linked_elderly_ids）
- doctor：能看到授权患者的数据（user_id in authorized_patient_ids）
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import User, FamilyLink, DoctorPatient


def get_linked_elderly_ids(family_id: str, db: Session) -> list:
    """获取家属绑定的所有老人 user_id 列表"""
    links = (
        db.query(FamilyLink)
        .filter(FamilyLink.family_user_id == family_id, FamilyLink.is_active == True)
        .all()
    )
    return [link.elderly_user_id for link in links]


def get_authorized_patient_ids(doctor_id: str, db: Session) -> list:
    """获取医生被授权的所有患者 user_id 列表"""
    auths = (
        db.query(DoctorPatient)
        .filter(DoctorPatient.doctor_id == doctor_id, DoctorPatient.is_active == True)
        .all()
    )
    return [auth.patient_id for auth in auths]


def filter_by_permission(query, current_user: User, db: Session):
    """按当前用户角色过滤查询： elderly / family / doctor

    使用方式：
        query = db.query(Session)
        query = filter_by_permission(query, current_user, db)
        results = query.all()
    """
    if not current_user or not current_user.id:
        raise HTTPException(status_code=403, detail="未认证用户")

    role = current_user.role

    if role == "admin":
        return query

    entity = query.column_descriptions[0]["entity"]

    # 处理无 user_id 的模型（如 VoiceMessage：sender_id / receiver_id）
    has_user_id = hasattr(entity, "user_id")
    has_sender_id = hasattr(entity, "sender_id")
    has_receiver_id = hasattr(entity, "receiver_id")

    if not has_user_id and has_sender_id and has_receiver_id:
        # VoiceMessage 等消息模型：能看到自己发送或收到的
        if role == "elderly":
            return query.filter(or_(entity.sender_id == current_user.id, entity.receiver_id == current_user.id))
        if role == "family":
            linked = get_linked_elderly_ids(current_user.id, db)
            allowed_ids = linked + [current_user.id]
            return query.filter(or_(entity.sender_id.in_(allowed_ids), entity.receiver_id.in_(allowed_ids)))
        if role == "doctor":
            patients = get_authorized_patient_ids(current_user.id, db)
            allowed_ids = patients + [current_user.id]
            return query.filter(or_(entity.sender_id.in_(allowed_ids), entity.receiver_id.in_(allowed_ids)))
        return query.filter(or_(entity.sender_id == current_user.id, entity.receiver_id == current_user.id))

    # 标准模型（有 user_id）
    if role == "elderly":
        return query.filter(entity.user_id == current_user.id)

    if role == "family":
        linked = get_linked_elderly_ids(current_user.id, db)
        allowed_ids = linked + [current_user.id]
        return query.filter(entity.user_id.in_(allowed_ids))

    if role == "doctor":
        patients = get_authorized_patient_ids(current_user.id, db)
        allowed_ids = patients + [current_user.id]
        return query.filter(entity.user_id.in_(allowed_ids))

    return query.filter(entity.user_id == current_user.id)


def require_permission(user_id: str, current_user: User, db: Session):
    """显式检查 current_user 是否有权访问 user_id 的数据。
    无权时抛出 HTTP 403。"""
    if not current_user or not current_user.id:
        raise HTTPException(status_code=403, detail="未认证用户")

    if current_user.role == "admin":
        return

    if current_user.id == user_id:
        return

    if current_user.role == "family":
        linked = get_linked_elderly_ids(current_user.id, db)
        if user_id in linked:
            return

    if current_user.role == "doctor":
        patients = get_authorized_patient_ids(current_user.id, db)
        if user_id in patients:
            return

    raise HTTPException(status_code=403, detail="无权访问该用户数据")
