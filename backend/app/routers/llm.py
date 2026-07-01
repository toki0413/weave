# ============ LLM 路由：总结 / 情感分析 / 智能问答 ============
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging
import json as _json

from app.database import get_db
from app.models import Session as DBSession, User
from app.routers.auth import get_current_user
from app.services.llm_client import llm_call, llm_call_json, is_llm_available
from app.config import get_settings

logger = logging.getLogger("cognitive_garden")
router = APIRouter(prefix="/llm", tags=["llm"])

# ---------- 共享工具 ----------

def _check_llm_or_503():
    """如果 LLM 未配置，抛出 503"""
    if not is_llm_available():
        raise HTTPException(status_code=503, detail="LLM 未配置")

def _sanitize_narrative(text: str) -> str:
    """简单脱敏：移除常见姓名，保留叙事内容"""
    # 这里只做基础替换，真实场景可接入更完善的 PII 检测
    # 移除 "我叫..." 等自我介绍
    import re
    text = re.sub(r"我叫[\u4e00-\u9fff]{1,4}", "我叫（称呼）", text)
    text = re.sub(r"我的名字是[\u4e00-\u9fff]{1,4}", "我的名字是（称呼）", text)
    return text


def _get_recent_sessions(db: Session, user_id: str, days: int = 30) -> List[DBSession]:
    """获取用户最近 N 天的会话列表，按时间倒序"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.query(DBSession)
        .filter(
            DBSession.user_id == user_id,
            DBSession.created_at >= cutoff,
        )
        .order_by(DBSession.created_at.desc())
        .all()
    )


# ---------- 请求模型（简单 dict，也可以用 Pydantic）----------
from pydantic import BaseModel

class SummarizeRequest(BaseModel):
    narratives: Optional[List[str]] = None
    days: int = 7

class EmotionRequest(BaseModel):
    text: str

class QARequest(BaseModel):
    question: str
    user_id: Optional[str] = None

# ---------- 路由 ----------

@router.post("/summarize")
def summarize_memory(
    req: SummarizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    多天长记忆总结：将老人最近几天的记忆片段编织成一段连贯的故事。
    如果 narratives 为空，自动从数据库拉取最近会话。
    """
    _check_llm_or_503()

    narratives = req.narratives
    if not narratives:
        sessions = _get_recent_sessions(db, current_user.id, days=req.days)
        # 只取已加密或明文叙事；若加密则尝试解密（简化：直接取 narrative 字段）
        narratives = []
        for s in sessions:
            if s.narrative:
                narratives.append(s.narrative)
        narratives = list(reversed(narratives))  # 按时间正序

    if not narratives:
        return {"summary": "最近没有记录到记忆片段。"}

    # 脱敏
    sanitized = [_sanitize_narrative(n) for n in narratives]
    bullet_text = "\n".join(f"- {n}" for n in sanitized)

    prompt = (
        "请用温暖的中文，将以下老人一周的记忆片段编织成一段连贯的故事。"
        "保持叙事流畅，不要逐条复述，突出主要活动和情感氛围。"
        "控制在 300 字以内。\n\n"
        f"{bullet_text}"
    )

    try:
        summary = llm_call(prompt, temperature=0.7, max_tokens=512)
        return {"summary": summary}
    except Exception as e:
        logger.error("LLM summarize 失败: %s", e)
        raise HTTPException(status_code=503, detail="AI 总结服务暂时不可用，请稍后重试")


@router.post("/emotion")
def analyze_emotion_llm(
    req: EmotionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    LLM 情感分析：比规则分析更精准。
    返回格式与 emotion_analyzer 兼容：{overall, score, words}
    """
    _check_llm_or_503()

    text = _sanitize_narrative(req.text)

    system_prompt = (
        "你是一个情感分析助手。请分析以下中文文本的情感，"
        "仅返回 JSON 格式，不要添加任何解释。"
        "格式：{\"overall\": \"positive\"|\"neutral\"|\"negative\", "
        "\"score\": -1 到 1 之间的浮点数, "
        "\"words\": {\"positive\": [\"词1\", \"词2\"], \"negative\": [\"词3\", \"词4\"]}}"
    )

    try:
        result = llm_call_json(
            text,
            temperature=0.0,
            max_tokens=256,
            system_prompt=system_prompt,
        )
        # 校验并标准化
        overall = result.get("overall", "neutral")
        if overall not in ("positive", "neutral", "negative"):
            overall = "neutral"
        score = float(result.get("score", 0))
        score = max(-1.0, min(1.0, score))
        words = result.get("words", {"positive": [], "negative": []})
        return {
            "overall": overall,
            "score": round(score, 3),
            "words": {
                "positive": words.get("positive", []),
                "negative": words.get("negative", []),
            },
        }
    except Exception as e:
        logger.error("LLM emotion 失败: %s", e)
        raise HTTPException(status_code=503, detail="AI 情感分析服务暂时不可用")


@router.post("/qa")
def qa_from_memory(
    req: QARequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    智能问答：基于用户最近 30 天的会话记录回答问题。
    返回 {answer, sources: [session_id, ...]}
    """
    _check_llm_or_503()

    target_user_id = req.user_id or current_user.id
    # 安全检查：普通用户只能查自己的记录
    if target_user_id != current_user.id and current_user.role not in ("family", "doctor", "admin"):
        raise HTTPException(status_code=403, detail="无权查询该用户的记忆")

    sessions = _get_recent_sessions(db, target_user_id, days=30)
    if not sessions:
        return {"answer": "最近 30 天内没有记录到记忆内容。", "sources": []}

    # 构造上下文：每个会话取脱敏后的叙事和日期
    context_lines = []
    source_ids = []
    for s in reversed(sessions):  # 时间正序
        if not s.narrative:
            continue
        date_str = s.created_at.strftime("%Y-%m-%d") if s.created_at else "未知日期"
        safe_text = _sanitize_narrative(s.narrative)
        # 截断过长的单条记录，避免 prompt 超限
        if len(safe_text) > 200:
            safe_text = safe_text[:200] + "..."
        context_lines.append(f"[{date_str}] {safe_text}")
        source_ids.append(s.id)

    if not context_lines:
        return {"answer": "最近 30 天内的记录内容为空。", "sources": []}

    context_text = "\n".join(context_lines)
    question = req.question

    prompt = (
        "你是一位温和的认知助手。以下是一位老人最近 30 天的记忆记录（已脱敏处理）。\n"
        "请仅根据提供的记录内容回答问题，不要编造任何未在记录中出现的信息。"
        "如果记录中没有相关信息，请诚实说明。"
        "回答控制在 200 字以内。\n\n"
        f"记录：\n{context_text}\n\n"
        f"问题：{question}"
    )

    try:
        answer = llm_call(prompt, temperature=0.3, max_tokens=512)
        return {"answer": answer, "sources": source_ids[:10]}
    except Exception as e:
        logger.error("LLM QA 失败: %s", e)
        raise HTTPException(status_code=503, detail="AI 问答服务暂时不可用，请稍后重试")
