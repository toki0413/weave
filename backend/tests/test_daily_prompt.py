"""60 秒日课服务测试"""
from datetime import date

from app.services.daily_prompt import get_daily_prompt, TOPIC_POOL


def test_pool_wellformed():
    """题库契约：四类实体覆盖、口语短句、无书面句号"""
    assert len(TOPIC_POOL) >= 10
    cats = {t["category"] for t in TOPIC_POOL}
    assert {"person", "place", "event", "item"} <= cats
    for t in TOPIC_POOL:
        assert t["question"] and t["tts"]
        # 适老化：TTS 文本是短口语，不含书面句号
        assert "。" not in t["tts"]
        assert len(t["tts"]) <= 20


def test_deterministic_per_user_day():
    """同一用户同一天题目稳定（日期种子轮转）"""
    a1 = get_daily_prompt("user-a", date(2026, 10, 20), use_llm=False)
    a2 = get_daily_prompt("user-a", date(2026, 10, 20), use_llm=False)
    assert a1["topic"] == a2["topic"]
    assert a1["question"] == a2["question"]


def test_topic_changes_by_day():
    """不同日期大概率轮换到不同题目（14 题池，撞题概率低但允许）"""
    seen = {get_daily_prompt("user-a", date(2026, 10, d), use_llm=False)["topic"] for d in range(1, 8)}
    assert len(seen) >= 3


def test_multimodal_contract():
    """多模态契约：voice 主通道 + text 大字 + haptic 起止 + 时长提示"""
    p = get_daily_prompt("user-a", date(2026, 10, 20), use_llm=False)
    assert p["modality"]["voice"] == "primary"
    assert p["modality"]["text"] == "large_print"
    assert p["duration_hint"] == "60秒"


def test_llm_fallback_silent():
    """未配置 LLM 时静默回退题库原题，个性化字段为空"""
    p = get_daily_prompt("user-a", date(2026, 10, 20), use_llm=True)
    assert p["personalized_hint"] is None
    assert p["llm_provider"] is None
    assert p["question"]
