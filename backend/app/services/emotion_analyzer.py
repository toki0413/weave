# ============ 情感分析服务：jieba 分词 + 情感词典 + 可选 LLM 增强 ============
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.config import get_settings
from app.services.llm_client import llm_call_json, is_llm_available

logger = logging.getLogger("cognitive_garden")

# 情感词典
POSITIVE_WORDS = ["开心", "快乐", "高兴", "满足"]
NEGATIVE_WORDS = ["难过", "担心", "孤独", "害怕", "痛苦"]

# 尝试加载 jieba，nlp.py 已保证全局可用，这里直接复用
try:
    import jieba
    import jieba.posseg as pseg
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger.warning("jieba 未安装，情感分析降级到纯词典匹配")


def _segment_text(text: str) -> List[str]:
    """分词，优先 jieba"""
    if JIEBA_AVAILABLE:
        return list(jieba.cut(text))
    # 纯字符滑动窗口降级（只覆盖词典词）
    words = []
    i = 0
    while i < len(text):
        matched = False
        for j in range(min(8, len(text) - i), 0, -1):
            sub = text[i:i + j]
            if sub in POSITIVE_WORDS or sub in NEGATIVE_WORDS:
                words.append(sub)
                i += j
                matched = True
                break
        if not matched:
            words.append(text[i])
            i += 1
    return words


def _llm_analyze_emotion(text: str) -> Optional[Dict[str, Any]]:
    """如果配置了 LLM，尝试调用 LLM 做更精准的情感分析"""
    if not is_llm_available():
        return None

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
        logger.warning("LLM 情感分析失败，回退到规则分析: %s", e)
    return None


def analyze_emotion(text: str) -> Dict[str, Any]:
    """
    分析文本情感。
    1. 优先尝试 LLM（如果配置了 LLM_PROVIDER）
    2. 回退到规则分析：jieba 分词 + 情感词典匹配
    返回: {overall: 'positive'|'neutral'|'negative', score: float, words: {positive: [], negative: []}}
    """
    # 先尝试 LLM
    llm_result = _llm_analyze_emotion(text)
    if llm_result is not None:
        return llm_result

    # 规则分析
    words = _segment_text(text)
    positive = [w for w in words if w in POSITIVE_WORDS]
    negative = [w for w in words if w in NEGATIVE_WORDS]

    pos_count = len(positive)
    neg_count = len(negative)
    score = (pos_count - neg_count) / (pos_count + neg_count + 1)

    if score > 0.1:
        overall = "positive"
    elif score < -0.1:
        overall = "negative"
    else:
        overall = "neutral"

    return {
        "overall": overall,
        "score": round(score, 3),
        "words": {
            "positive": positive,
            "negative": negative,
        },
    }


def analyze_emotion_trend(sessions: List[Any]) -> List[Dict[str, Any]]:
    """
    输入会话列表（ORM 对象或 dict），返回每日情绪分数数组，用于趋势图。
    按日期（日历日）聚合，同一天取平均分。
    """
    if not sessions:
        return []

    from collections import defaultdict

    day_scores = defaultdict(list)
    for s in sessions:
        # 支持 ORM 对象和 dict
        created_at = s.created_at if hasattr(s, "created_at") else s.get("created_at")
        emotion_score = s.emotion_score if hasattr(s, "emotion_score") else s.get("emotion_score")
        if created_at is None or emotion_score is None:
            continue
        dt = created_at
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        day_key = dt.strftime("%Y-%m-%d")
        day_scores[day_key].append(float(emotion_score))

    trend = []
    for day in sorted(day_scores.keys()):
        scores = day_scores[day]
        avg_score = sum(scores) / len(scores)
        trend.append({
            "date": day,
            "score": round(avg_score, 3),
            "label": day[5:].replace("-", "/"),  # MM/DD
        })
    return trend
