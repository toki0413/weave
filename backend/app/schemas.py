from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

# ========== Auth ==========
class UserCreate(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6)
    role: str = "elderly"
    name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("密码需包含至少一位数字")
        if not any(c.isalpha() for c in v):
            raise ValueError("密码需包含至少一位字母")
        return v


class UserLogin(BaseModel):
    phone: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    recovery_code: Optional[str] = None  # 仅注册时返回一次

class UserOut(BaseModel):
    id: str
    phone: str
    role: str
    name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ========== Session ==========
class NarrativeInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    dialect: Optional[str] = "mandarin"

class SessionCreate(BaseModel):
    day_number: int = 1
    narrative_input: NarrativeInput
    metrics: Optional[Dict[str, Any]] = None  # 前端可传预计算指标
    audio_metrics: Optional[Dict[str, Any]] = None  # 语音认知指标（录音时传入）

# ========== Graph / Metrics ==========
class GraphData(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class SessionWithMetrics(BaseModel):
    """前端带指标的会话创建（离线模式下前端计算后上传）"""
    day_number: int = 1
    narrative_input: NarrativeInput
    graph: Optional[GraphData] = None
    metrics: Optional[Dict[str, Any]] = None
    health_score: Optional[int] = None
    anomalies: Optional[List[Dict[str, Any]]] = None

class SessionOut(BaseModel):
    id: str
    user_id: str
    day_number: int
    narrative: str
    graph: Dict[str, Any]
    metrics: Dict[str, Any]
    health_score: int
    anomalies: List[Dict[str, Any]]
    emotion_score: Optional[float] = None
    emotion_label: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ========== Training ==========
class TrainingRecordCreate(BaseModel):
    game_type: str = Field(..., min_length=1, max_length=50)
    score: int = Field(..., ge=0)

class TrainingRecordOut(BaseModel):
    id: str
    user_id: str
    game_type: str
    score: int
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ========== Graph / Metrics ==========
class HealthMetrics(BaseModel):
    connectivity: float
    clustering: float
    centrality: float
    entropy: float
    density: float
    avg_path_len: float
    global_eff: float
    small_world: float
    node_count: int
    edge_count: int
    anon_count: int

class BaselineCreate(BaseModel):
    session_id: str

class BaselineOut(BaseModel):
    id: str
    user_id: str
    session_id: str
    metrics: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ========== Voice Message ==========
class VoiceMessageCreate(BaseModel):
    receiver_id: str
    audio_base64: str
    duration: int = 0

class VoiceMessageOut(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    audio_url: str
    duration: int
    created_at: datetime
    is_read: bool
    encrypted_payload: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

# ========== Share Record ==========
class ShareCreate(BaseModel):
    message: Optional[str] = None

class ShareRecordOut(BaseModel):
    id: str
    session_id: str
    elderly_id: str
    family_id: str
    shared_at: datetime
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class StatePayload(BaseModel):
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_id_counter: int = 0
    current_day: int = 0
    day_snapshots: Dict[str, Any] = {}
    baseline_metrics: Optional[Dict[str, Any]] = None
    welcome_dismissed: bool = False
