from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
import logging
from app.database import get_db
from app.models import Session as DBSession, User, CustomLexicon, Baseline
from app.schemas import SessionCreate, SessionOut, SessionWithMetrics
from app.routers.auth import get_current_user
from app.rate_limit import rate_limit
from app.services.nlp import parse_narrative
from app.services.metrics import compute_metrics_from_graph
from app.services.health import compute_health
from app.services.notification_service import create_anomaly_notification, create_emotion_notification
from app.services.events import broadcast_event, add_event_queue, remove_event_queue
from app.services.crypto import encrypt, decrypt
import asyncio
from app.middleware.permission import filter_by_permission, require_permission
from app.services.sync_protocol import _get_device_sync, _increment_vector_clock
from app.services.temporal_parser import resolve_day_number

logger = logging.getLogger("cognitive_garden")
from app.services import key_manager

router = APIRouter(prefix="/session", tags=["session"])

# low_confidence 判定阈值：stt.py 的启发式置信度（字符密度线性映射，0-1）低于
# 此值视为低置信。这是拍的试点参数，不是标定值——试点期 low_confidence 的
# 真实分布会告诉我们该定在哪（见 weekly_baseline / baseline_personal 的剔除逻辑）。
LOW_CONFIDENCE_THRESHOLD = 0.5


def _compute_day_number(db: Session, user_id: str) -> int:
    """"参加的第 N 天"：首条会话日到今天（UTC 日历差）+ 1，首条即第 1 天。

    day_number <= 0 是前端"未指定"哨兵（老人端此前恒传 0），此时由后端计算，
    单一事实源、与 pilot_export 的周桶互不依赖。显式 >0 的值照旧透传
    （full 模式的 parse.js 自算天数、测试 seeding）。
    已知局限：按 UTC 日历日切天，对 UTC+8 用户在 0:00-8:00 之间与直觉差一天；
    day_number 只作进度展示，不承载数据合同（周桶按 created_at 分桶），可接受。
    """
    first = (
        db.query(DBSession.created_at)
        .filter(DBSession.user_id == user_id)
        .order_by(DBSession.created_at.asc())
        .first()
    )
    if first is None or first[0] is None:
        return 1
    now = datetime.now(timezone.utc)
    return max(1, (now.date() - first[0].date()).days + 1)


def _load_custom_words(db: Session, user_id: str):
    """从数据库加载该用户的自定义词典，转成 NLP 服务需要的格式"""
    rows = db.query(CustomLexicon).filter(CustomLexicon.user_id == user_id).all()
    return [{"word": r.word, "type": r.word_type} for r in rows]


def _require_key(user_id: str) -> bytes:
    """拿当前用户的业务主密钥，没缓存就提示重新登录"""
    try:
        return key_manager.get_user_key(user_id)
    except RuntimeError:
        raise HTTPException(status_code=401, detail="加密密钥不可用，请重新登录")


def _decrypt_with_fallback(ciphertext: str, user_id: str) -> str:
    """解密业务字段：先用主密钥，失败再用KEK回退（兼容旧数据）"""
    try:
        master_key = key_manager.get_user_key(user_id)
        return decrypt(ciphertext, master_key)
    except Exception:
        pass

    try:
        kek = key_manager.get_user_kek(user_id)
        return decrypt(ciphertext, kek)
    except Exception:
        raise HTTPException(status_code=401, detail="无法解密数据，请重新登录")


def _decrypt_session(session: DBSession, user_id: str) -> DBSession:
    """如果会话已加密，就地解密 narrative 字段；旧数据直接放过"""
    if session.is_encrypted:
        session.narrative = _decrypt_with_fallback(session.narrative, user_id)
    return session


@router.post("/", response_model=SessionOut, dependencies=[rate_limit(20, 60)])
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 把用户自定义词典带进 NLP，让家人名字、常去地点等能被识别
    custom_words = _load_custom_words(db, current_user.id)
    nlp_result = parse_narrative(data.narrative_input.text, custom_words)
    graph = build_graph(nlp_result["entities"], nlp_result["relations"])

    # 如果前端传了预计算指标，直接用；否则后端实时计算
    if data.metrics:
        metrics = data.metrics
    else:
        metrics = compute_metrics_from_graph(graph)

    # 语音认知指标：存入 metrics.audio，供趋势分析使用
    if data.audio_metrics:
        metrics["audio"] = data.audio_metrics

    # 时间实体解析：若存在历史时间引用且 day_number 为默认值 1，自动调整
    # day_number <= 0 视为"未指定"（老人端哨兵），由后端按首条会话日起算
    temporal_refs = nlp_result.get("temporal_references", [])
    if data.day_number <= 0:
        day_number = _compute_day_number(db, current_user.id)
    else:
        day_number = data.day_number
    if temporal_refs and day_number == 1:
        max_day_row = (
            db.query(DBSession)
            .filter(DBSession.user_id == current_user.id)
            .with_entities(DBSession.day_number)
            .order_by(DBSession.day_number.desc())
            .first()
        )
        current_max_day = max_day_row[0] if max_day_row else 0
        offset = resolve_day_number(temporal_refs, datetime.now())
        if offset is not None and offset < 0:
            adjusted = max(1, current_max_day + offset)
            if adjusted >= 1 and adjusted != day_number:
                day_number = adjusted
                logger.info(
                    "用户 %s 时间引用触发 day_number 调整: %d → %d (offset=%d)",
                    current_user.id, data.day_number, day_number, offset,
                )

    # 个人基线：查询已有基线，若历史 >= 7 条则重建
    history_count = (
        db.query(DBSession)
        .filter(DBSession.user_id == current_user.id)
        .count()
    )
    personal_baseline = None
    if history_count >= 7:
        personal_baseline = build_personal_baseline(current_user.id, db)
    if not personal_baseline:
        # 回退：使用已有个人基线（即使本次未重建）
        baseline_row = (
            db.query(Baseline)
            .filter(
                Baseline.user_id == current_user.id,
                Baseline.session_id.is_(None),
            )
            .first()
        )
        if baseline_row and baseline_row.personal_mean:
            personal_baseline = {
                "personal_mean": baseline_row.personal_mean,
                "personal_std": baseline_row.personal_std,
                "sample_count": baseline_row.sample_count,
            }

    if personal_baseline:
        metrics["baseline"] = personal_baseline

    health_score = compute_health(
        metrics,
        nlp_result["anomalies"],
        None,
        [],
        personal_baseline=personal_baseline,
    )

    # 叙事文本入库前加密
    key = _require_key(current_user.id)
    encrypted_narrative = encrypt(data.narrative_input.text, key)

    db_session = DBSession(
        user_id=current_user.id,
        day_number=day_number,
        narrative=encrypted_narrative,
        graph=graph,
        metrics=metrics,
        health_score=health_score,
        anomalies=nlp_result["anomalies"],
        is_encrypted=True,
        temporal_references=temporal_refs if temporal_refs else None,
        emotion_score=nlp_result["emotion"]["score"],
        emotion_label=nlp_result["emotion"]["overall"],
        # 来源归因（日课漏斗第三步）：白名单外一律记 manual
        source=data.source if data.source in ("daily_prompt", "manual", "share", "import") else "manual",
        # ASR 溯源（0018）：只在真走过 /stt/transcribe 时才有值；
        # 手动输入/浏览器无音频路径不传 → 保持 NULL（"未知"），不编造。
        # low_confidence 三态：True 低置信 / False 已知可信 / NULL 无 ASR（未知），
        #   剔除逻辑只认 True（baseline_personal），NULL 绝不当 False 用。
        # asr_duration_sec 取音频指标的时长；无音频则 NULL。
        asr_provider=(data.asr_provider or "").strip()[:20] or None,
        asr_confidence=data.asr_confidence,
        low_confidence=(
            bool(data.asr_confidence < LOW_CONFIDENCE_THRESHOLD)
            if data.asr_confidence is not None
            else None
        ),
        asr_duration_sec=(
            float(data.audio_metrics["duration_sec"])
            if data.audio_metrics and data.audio_metrics.get("duration_sec") is not None
            else None
        ),
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)

    # 更新 DeviceSync 向量时钟（设备 ID 从请求头获取，若无可降级）
    try:
        device_id = "default"  # 可扩展为从请求头读取
        sync = _get_device_sync(current_user.id, device_id, db)
        sync.vector_clock = _increment_vector_clock(sync.vector_clock, device_id)
        sync.last_sync_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        pass

    # 检测到异常时给绑定的家属发通知；失败不影响会话创建
    if nlp_result.get("anomalies"):
        try:
            create_anomaly_notification(current_user.id, nlp_result["anomalies"], db, session_id=db_session.id)
        except Exception as e:
            logger.warning("发送异常通知失败: %s", e, exc_info=True)

    # 连续 3 天消极情绪通知
    if nlp_result.get("emotion", {}).get("overall") == "negative":
        try:
            _check_consecutive_negative_emotion(current_user.id, db, session_id=db_session.id)
        except Exception as e:
            logger.warning("检查消极情绪通知失败: %s", e, exc_info=True)

    # 返回给前端的是明文
    db_session.narrative = data.narrative_input.text

    # 广播新会话事件到 SSE（家属端可订阅）
    try:
        broadcast_event({
            "type": "new_session",
            "elderly_id": current_user.id,
            "data": {
                "session_id": db_session.id,
                "day_number": db_session.day_number,
                "summary": data.narrative_input.text[:100] + ("..." if len(data.narrative_input.text) > 100 else "")
            }
        })
    except Exception:
        pass

    return db_session

@router.get("/", response_model=List[SessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 30,
):
    query = db.query(DBSession)
    query = filter_by_permission(query, current_user, db)
    sessions = query.order_by(DBSession.created_at.desc()).limit(limit).all()
    return [_decrypt_session(s, current_user.id) for s in sessions]

@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(DBSession).filter(
        DBSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    require_permission(session.user_id, current_user, db)
    return _decrypt_session(session, current_user.id)

@router.get("/trend/health")
def get_health_trend(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
):
    sessions = db.query(DBSession).filter(
        DBSession.user_id == current_user.id
    ).order_by(DBSession.created_at.desc()).limit(days).all()

    trend = [
        {
            "date": s.created_at.isoformat(),
            "day": s.day_number,
            "health": s.health_score,
            "anomalies": len(s.anomalies) if s.anomalies else 0,
        }
        for s in reversed(sessions)
    ]
    return {"trend": trend}


@router.get("/trend/emotion")
def get_emotion_trend(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = 30,
):
    from app.services.emotion_analyzer import analyze_emotion_trend

    sessions = db.query(DBSession).filter(
        DBSession.user_id == current_user.id,
        DBSession.emotion_score.isnot(None),
    ).order_by(DBSession.created_at.desc()).limit(days).all()

    trend = analyze_emotion_trend(sessions)
    return {"trend": trend}

# 图谱构建
def build_graph(entities, relations):
    nodes = []
    edges = []
    node_id = 0
    node_map = {}

    for cat, items in entities.items():
        for item in items:
            node_id += 1
            node_map[f"{cat}:{item}"] = node_id
            nodes.append({
                "id": node_id,
                "label": item,
                "type": cat.rstrip("s"),
            })

    for rel in relations:
        if rel["from"] in node_map and rel["to"] in node_map:
            edges.append({
                "from": node_map[rel["from"]],
                "to": node_map[rel["to"]],
                "type": rel.get("type", "custom"),
            })

    return {"nodes": nodes, "edges": edges}


def _check_consecutive_negative_emotion(user_id: str, db: Session, session_id: str):
    """检查最近 3 个日历日是否连续消极，若是则给家属发通知"""
    from datetime import timedelta

    # 取最近 30 天内所有会话（按日期倒序）
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    sessions = (
        db.query(DBSession)
        .filter(
            DBSession.user_id == user_id,
            DBSession.created_at >= cutoff,
            DBSession.emotion_label.isnot(None),
        )
        .order_by(DBSession.created_at.desc())
        .all()
    )

    if not sessions:
        return

    # 按日历日分组，取每天最消极的标签（negative > neutral > positive）
    from collections import defaultdict
    day_emotions = defaultdict(list)
    for s in sessions:
        day_key = s.created_at.strftime("%Y-%m-%d")
        day_emotions[day_key].append(s.emotion_label)

    # 取每天的优先级最高（最消极）标签
    rank = {"negative": 2, "neutral": 1, "positive": 0}
    daily = []
    for day in sorted(day_emotions.keys(), reverse=True):
        labels = day_emotions[day]
        worst = max(labels, key=lambda l: rank.get(l, 0))
        daily.append({"day": day, "label": worst})

    # 检查最近 3 个有记录的日历日是否连续且都是 negative
    # "连续"定义为日历日连续
    if len(daily) >= 3:
        d0 = datetime.strptime(daily[0]["day"], "%Y-%m-%d").date()
        d1 = datetime.strptime(daily[1]["day"], "%Y-%m-%d").date()
        d2 = datetime.strptime(daily[2]["day"], "%Y-%m-%d").date()
        if (d0 - d1).days == 1 and (d1 - d2).days == 1:
            if daily[0]["label"] == "negative" and daily[1]["label"] == "negative" and daily[2]["label"] == "negative":
                create_emotion_notification(user_id, daily[0]["day"], daily[2]["day"], db, session_id=session_id)
