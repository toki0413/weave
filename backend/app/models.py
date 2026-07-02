import uuid
from datetime import datetime, timezone

def _utc_now():
    return datetime.now(timezone.utc)
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Enum, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # username 作为主登录标识，phone 改为可选（便于家属关联或短信通知）
    username = Column(String(50), unique=True, index=True, nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum("elderly", "family", "doctor", "admin", name="user_role"), default="elderly")
    name = Column(String(100))
    # 加密相关：注册时生成的随机 salt，用于从密码派生加密密钥（KEK）
    encryption_salt = Column(String(64))
    # 主密钥（业务数据加密用）经 KEK 加密后的密文
    master_key_encrypted = Column(Text)
    # 恢复码哈希，用于忘记密码时验证恢复码
    recovery_code_hash = Column(String(255))
    # 经恢复码派生密钥加密后的主密钥（与 recovery_code_hash 配对）
    recovery_master_key_encrypted = Column(Text)
    # 恢复码派生密钥用的 salt
    recovery_salt = Column(String(64))
    created_at = Column(DateTime, default=_utc_now)
    
    sessions = relationship("Session", back_populates="user")
    baselines = relationship("Baseline", back_populates="user")
    recovery_requests = relationship(
        "RecoveryRequest",
        foreign_keys="RecoveryRequest.user_id",
        back_populates="user",
    )

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    day_number = Column(Integer, default=1)
    narrative = Column(Text)  # 加密后存密文（base64），未加密则是明文
    graph = Column(JSON)  # { nodes: [...], edges: [...] }
    metrics = Column(JSON)  # computeMetrics result
    health_score = Column(Integer)
    anomalies = Column(JSON)  # [{ event, severity, ... }]
    # 标记 narrative 是否已加密，兼容旧数据
    is_encrypted = Column(Boolean, default=False)
    # 时间实体解析结果（用于自动调整 day_number）
    temporal_references = Column(JSON, nullable=True)
    # 情感分析结果
    emotion_score = Column(Float, nullable=True)  # 浮点数 -1 ~ 1
    emotion_label = Column(String(20), nullable=True)  # positive / neutral / negative
    created_at = Column(DateTime, default=_utc_now)
    
    user = relationship("User", back_populates="sessions")

class Baseline(Base):
    __tablename__ = "baselines"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    session_id = Column(String(36), ForeignKey("sessions.id"))
    metrics = Column(JSON)
    # 个人基线字段：基于用户历史会话的自适应均值/标准差
    personal_mean = Column(JSON, nullable=True)
    personal_std = Column(JSON, nullable=True)
    sample_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utc_now)
    
    user = relationship("User", back_populates="baselines")

class UserState(Base):
    __tablename__ = "user_states"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)
    node_id_counter = Column(Integer, default=0)
    current_day = Column(Integer, default=0)
    day_snapshots = Column(JSON, default=dict)
    baseline_metrics = Column(JSON, nullable=True)
    welcome_dismissed = Column(Integer, default=0)  # 0/1 for SQLite boolean
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)
    
    user = relationship("User")

class ScaleRecord(Base):
    """认知量表评估记录"""
    __tablename__ = "scale_records"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    scale_type = Column(String(20), nullable=False)  # mmse / ad8
    answers = Column(JSON)  # 加密后存密文字符串，未加密则是 [{ question_id, score }]
    total_score = Column(Integer, nullable=False)
    interpretation = Column(String(50))  # 解读等级
    # 标记 answers 是否已加密，兼容旧数据
    is_encrypted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utc_now)
    
    user = relationship("User")


class CustomLexicon(Base):
    """用户自定义词典：每个家庭专属的实体（家人名字、常去地点等）"""
    __tablename__ = "custom_lexicon"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    word = Column(String(100), nullable=False)
    word_type = Column(Enum("person", "place", "event", "item", name="lexicon_word_type"), nullable=False)
    created_at = Column(DateTime, default=_utc_now)

    user = relationship("User")


class FamilyLink(Base):
    """家属-老人关联表：一个家属可以绑定多位老人，反向亦可"""
    __tablename__ = "family_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    elderly_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    family_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    relation = Column(String(50))  # 子女/配偶/其他
    is_active = Column(Boolean, default=True)  # 绑定是否有效
    created_at = Column(DateTime, default=_utc_now)

    elderly = relationship("User", foreign_keys=[elderly_user_id])
    family = relationship("User", foreign_keys=[family_user_id])


class DoctorPatient(Base):
    """医生-患者授权表：医生查看/编辑患者数据的权限"""
    __tablename__ = "doctor_patients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    doctor_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    patient_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    access_level = Column(String(20), default="read")  # read | read_write
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utc_now)

    doctor = relationship("User", foreign_keys=[doctor_id])
    patient = relationship("User", foreign_keys=[patient_id])


class DeviceSync(Base):
    """设备同步表：每用户每设备一个向量时钟"""
    __tablename__ = "device_syncs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(String(255), nullable=False, index=True)
    vector_clock = Column(JSON, default=dict)  # { device_id: timestamp }
    last_sync_at = Column(DateTime, default=_utc_now)
    created_at = Column(DateTime, default=_utc_now)

    user = relationship("User")

    __table_args__ = (
        # 确保同一用户同一设备只有一条记录
        __import__('sqlalchemy').UniqueConstraint("user_id", "device_id"),
    )


class Notification(Base):
    """家属端通知：异常/衰退/量表到期等提醒都走这里"""
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # anomaly / decline / scale_reminder
    title = Column(String(200), nullable=False)
    content = Column(Text)
    severity = Column(String(20), default="info")  # info / warning / danger
    related_data = Column(JSON)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utc_now)

    user = relationship("User")


class VoiceMessage(Base):
    """家属语音留言：家属发送给老人或老人发送给家属的语音消息"""
    __tablename__ = "voice_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    audio_url = Column(String(500), nullable=False)  # /uploads/{filename}
    duration = Column(Integer, default=0)  # 秒
    created_at = Column(DateTime, default=_utc_now)
    is_read = Column(Boolean, default=False)
    # 端到端加密：存储加密后的音频 payload（JSON: {ciphertext, iv, tag}）
    encrypted_payload = Column(JSON, nullable=True)

    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])


class ShareRecord(Base):
    """老人分享会话给家属的记录"""
    __tablename__ = "share_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    elderly_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    family_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    shared_at = Column(DateTime, default=_utc_now)
    message = Column(Text, nullable=True)  # 可选文字留言

    session = relationship("Session")
    elderly = relationship("User", foreign_keys=[elderly_id])
    family = relationship("User", foreign_keys=[family_id])


class RecoveryRequest(Base):
    """家属/医生发起的解密授权请求（离线场景下可人工审批）"""
    __tablename__ = "recovery_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending / approved / rejected
    reason = Column(Text)
    created_at = Column(DateTime, default=_utc_now)
    resolved_at = Column(DateTime)

    user = relationship("User", foreign_keys=[user_id], back_populates="recovery_requests")
    requester = relationship("User", foreign_keys=[requester_id])


class TrainingRecord(Base):
    """记忆训练游戏记录"""
    __tablename__ = "training_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    game_type = Column(String(50), nullable=False)  # memory_challenge / number_link
    score = Column(Integer, nullable=False)
    completed_at = Column(DateTime, default=_utc_now)

    user = relationship("User")


class RefreshToken(Base):
    """Refresh Token 持久化（支持主动吊销）

    access token 短期有效（30 分钟），通过 jti 黑名单吊销；
    refresh token 长期有效（7 天），通过本表记录并支持批量吊销。
    """
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # SHA-256 hex 摘要，避免明文 token 落库
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    device_id = Column(String(255), nullable=True)  # 设备标识（可选）
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    # null = 有效；非 null = 已吊销时间
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    user = relationship("User")


class AuditLog(Base):
    """操作审计日志（医疗数据合规要求）

    记录谁在什么时候访问/修改了谁的敏感数据。
    详见《个人信息保护法》《医疗机构数据安全管理办法》。
    """
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # 操作者（null = 匿名/系统操作）
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_role = Column(String(20), nullable=True)  # elderly/family/doctor/admin/system
    action = Column(String(50), nullable=False)  # login/register/view/update/delete/export/share
    resource_type = Column(String(50), nullable=True)  # session/scale_record/voice_message/user
    resource_id = Column(String(36), nullable=True)
    # 被访问数据所属的用户（医患场景下与 actor 不同）
    target_user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    status_code = Column(Integer, nullable=True)  # HTTP 响应码
    # 额外上下文（不记录敏感数据明文）
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utc_now, index=True)

    actor = relationship("User", foreign_keys=[actor_id])
    target = relationship("User", foreign_keys=[target_user_id])
