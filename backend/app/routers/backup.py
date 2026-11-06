"""数据备份与恢复：导出/导入用户全部数据为 JSON（gzip 压缩），以及导出日志"""
import json
import gzip
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from io import BytesIO
from app.database import get_db
from app.config import get_settings
from app.models import User, Session as SessionModel, Baseline, UserState
from app.routers.auth import get_current_user
from app.rate_limit import rate_limit

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/export", dependencies=[rate_limit(30, 60)])
async def export_data(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """导出当前用户的所有数据为 JSON 文件（gzip 压缩）"""
    sessions = db.query(SessionModel).filter(SessionModel.user_id == current_user.id).all()
    baselines = db.query(Baseline).filter(Baseline.user_id == current_user.id).all()
    state = db.query(UserState).filter(UserState.user_id == current_user.id).first()

    payload = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "username": current_user.username,
            "phone": current_user.phone,
            "name": current_user.name,
            "role": current_user.role,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "sessions": [
            {
                "id": s.id,
                "day_number": s.day_number,
                "narrative": s.narrative,
                "graph": s.graph,
                "metrics": s.metrics,
                "health_score": s.health_score,
                "anomalies": s.anomalies,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "is_encrypted": getattr(s, 'is_encrypted', False),
            }
            for s in sessions
        ],
        "baselines": [
            {
                "id": b.id,
                "session_id": b.session_id,
                "metrics": b.metrics,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in baselines
        ],
        "state": {
            "nodes": state.nodes if state else [],
            "edges": state.edges if state else [],
            "node_id_counter": state.node_id_counter if state else 0,
            "current_day": state.current_day if state else 0,
            "day_snapshots": state.day_snapshots if state else {},
            "baseline_metrics": state.baseline_metrics if state else None,
            "welcome_dismissed": state.welcome_dismissed if state else 0,
        } if state else None,
    }

    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    content = gzip.compress(json_bytes)
    filename = f"cognitive-garden-backup-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json.gz"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ========== 备份导入校验模型 ==========
class _BackupUser(BaseModel):
    username: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[str] = None


class _BackupSession(BaseModel):
    id: str
    day_number: int = 1
    narrative: Optional[str] = None
    graph: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    health_score: Optional[int] = None
    anomalies: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[str] = None
    is_encrypted: bool = False


class _BackupBaseline(BaseModel):
    id: str
    session_id: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


class _BackupState(BaseModel):
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_id_counter: int = 0
    current_day: int = 0
    day_snapshots: Dict[str, Any] = {}
    baseline_metrics: Optional[Dict[str, Any]] = None
    welcome_dismissed: int = 0


class _BackupPayload(BaseModel):
    version: str
    exported_at: Optional[str] = None
    user: _BackupUser
    sessions: List[_BackupSession] = []
    baselines: List[_BackupBaseline] = []
    state: Optional[_BackupState] = None

    model_config = ConfigDict(extra="ignore")


@router.post("/import", dependencies=[rate_limit(5, 300)])
async def import_data(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """从 JSON 文件恢复数据（覆盖当前用户的会话和状态），支持 .json 和 .json.gz"""
    if not file.filename or not (file.filename.endswith(".json") or file.filename.endswith(".json.gz")):
        raise HTTPException(status_code=400, detail="请上传 JSON 备份文件（.json 或 .json.gz）")

    settings = get_settings()
    max_bytes = settings.max_backup_import_mb * 1024 * 1024

    # 限量读取：即使客户端声明了超大 Content-Length，也只读上限 +1 字节
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"备份文件超过 {settings.max_backup_import_mb}MB 限制",
        )

    # 检测 gzip 并解压（分块 + 解压上限，防压缩炸弹）
    if file.filename.endswith(".json.gz"):
        try:
            decompressed_limit = max_bytes * 10
            out = BytesIO()
            with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                total = 0
                while True:
                    chunk = gz.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > decompressed_limit:
                        raise HTTPException(
                            status_code=413,
                            detail="备份文件解压后体积超出限制",
                        )
                    out.write(chunk)
            content = out.getvalue()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"gzip 解压失败: {e}")

    try:
        raw = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"JSON 格式错误: {e}")

    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="备份文件应为 JSON 对象")

    try:
        payload = _BackupPayload.model_validate(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"备份文件字段校验失败: {e}")

    # 备份匹配：优先 username，回退 phone（兼容旧备份文件）
    backup_user = payload.user
    matched = (
        (backup_user.username and backup_user.username == current_user.username)
        or (backup_user.phone and backup_user.phone == current_user.phone)
    )
    if not matched:
        raise HTTPException(status_code=403, detail="备份文件与当前账号不匹配")

    # 清除现有数据
    db.query(SessionModel).filter(SessionModel.user_id == current_user.id).delete()
    db.query(Baseline).filter(Baseline.user_id == current_user.id).delete()
    db.query(UserState).filter(UserState.user_id == current_user.id).delete()

    data = payload.model_dump()

    # 恢复会话
    for s in data.get("sessions", []):
        narrative = s.get("narrative")
        is_encrypted = s.get("is_encrypted", False)
        if not is_encrypted and narrative and isinstance(narrative, str):
            # heuristic: base64 ciphertext is typically long and has no spaces
            if len(narrative) > 40 and ' ' not in narrative.rstrip('='):
                is_encrypted = True
        session = SessionModel(
            id=s["id"],
            user_id=current_user.id,
            day_number=s.get("day_number", 1),
            narrative=narrative,
            graph=s.get("graph"),
            metrics=s.get("metrics"),
            health_score=s.get("health_score"),
            anomalies=s.get("anomalies"),
            is_encrypted=is_encrypted,
        )
        db.add(session)

    # 恢复基准
    for b in data.get("baselines", []):
        baseline = Baseline(
            id=b["id"],
            user_id=current_user.id,
            session_id=b.get("session_id"),
            metrics=b.get("metrics"),
        )
        db.add(baseline)

    # 恢复状态
    state_data = data.get("state")
    if state_data:
        state = UserState(
            user_id=current_user.id,
            nodes=state_data.get("nodes", []),
            edges=state_data.get("edges", []),
            node_id_counter=state_data.get("node_id_counter", 0),
            current_day=state_data.get("current_day", 0),
            day_snapshots=state_data.get("day_snapshots", {}),
            baseline_metrics=state_data.get("baseline_metrics"),
            welcome_dismissed=state_data.get("welcome_dismissed", 0),
        )
        db.add(state)

    db.commit()
    return {
        "status": "ok",
        "imported": {
            "sessions": len(data.get("sessions", [])),
            "baselines": len(data.get("baselines", [])),
        },
    }


@router.get("/logs", dependencies=[rate_limit(5, 300)])
async def export_logs(current_user: User = Depends(get_current_user)):
    """打包应用日志目录为 zip 供下载（用于技术支持排查）

    仅 admin：日志包含全站请求记录与错误堆栈，任意登录用户可取会构成
    横向越权（可见其他用户的活动痕迹）。
    """
    _require_admin(current_user)
    log_dir = Path.home() / ".cognitive-garden" / "logs"
    if not log_dir.exists():
        raise HTTPException(status_code=404, detail="暂无日志文件")

    log_files = [p for p in log_dir.iterdir() if p.is_file()]
    if not log_files:
        raise HTTPException(status_code=404, detail="暂无日志文件")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in log_files:
            arcname = f"logs/{f.name}"
            zf.write(f, arcname=arcname)
    buf.seek(0)

    filename = f"cognitive-garden-logs-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ========== KMS 恢复路径（gap 审计 G3）==========
# wrap key 丢失 = 全部 E2EE 内容永久不可解。密钥属于部署方而非终端用户，
# 三个端点一律 admin-only：status 自检、export 备份、import 灾后恢复。

class _KMSImportPayload(BaseModel):
    key_b64: str


def _require_admin(current_user: User) -> None:
    if (current_user.role or "") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作 KMS 密钥")


@router.get("/kms-status", dependencies=[rate_limit(10, 60)])
async def kms_status(current_user: User = Depends(get_current_user)):
    """KMS 恢复路径自检：provider 类型、备份可导出性、待办提示"""
    _require_admin(current_user)
    from app.services import kms
    return kms.describe_kms()


@router.get("/kms-wrap-key", dependencies=[rate_limit(3, 300)])
async def export_kms_key(current_user: User = Depends(get_current_user)):
    """导出 wrap key（base64）供部署方离线备份。

    非文件托管的 provider（env/aws）返回 409：密钥由外部体系管理，
    从对应密钥管理体系备份，不走本接口。
    """
    _require_admin(current_user)
    from app.services import kms
    try:
        key_b64 = kms.export_wrap_key()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "provider": "file",
        "key_b64": key_b64,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/kms-wrap-key", dependencies=[rate_limit(3, 300)])
async def import_kms_key(
    payload: _KMSImportPayload,
    current_user: User = Depends(get_current_user),
):
    """从备份恢复 wrap key（灾后恢复）：校验 → 落盘 → 热替换，无需重启"""
    _require_admin(current_user)
    from app.services import kms
    try:
        kms.import_wrap_key(payload.key_b64)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}
