"""60 秒日课服务测试"""
from datetime import date

import app.models as app_models
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


# ---- 冷启动种子序列（U1）：注册后前 7 天"家族人物 + 老物件"优先 ----

def test_seed_sequence_first_week_category_locked():
    """前 7 天类别按种子序列锁定：day0 家人、day1 老物件、day2 老朋友"""
    signup = date(2026, 11, 1)
    p0 = get_daily_prompt("user-a", signup, use_llm=False, signup_date=signup)
    p1 = get_daily_prompt("user-a", date(2026, 11, 2), use_llm=False, signup_date=signup)
    p2 = get_daily_prompt("user-a", date(2026, 11, 3), use_llm=False, signup_date=signup)
    assert p0["category"] == "person" and p0["seed_day"] == 0
    assert p1["category"] == "item" and p1["seed_day"] == 1
    assert p2["category"] == "person" and p2["seed_day"] == 2


def test_seed_window_exits_after_day7():
    """第 8 天起出窗口：seed_day 为 None，回到全池"""
    signup = date(2026, 11, 1)
    p = get_daily_prompt("user-a", date(2026, 11, 9), use_llm=False, signup_date=signup)
    assert p["seed_day"] is None
    assert p["question"]


def test_seed_deterministic_and_pool_narrowing():
    """种子期内同参稳定；且每类候选池非空（序列类别都存在于题库）"""
    cats = {t["category"] for t in TOPIC_POOL}
    from app.services.daily_prompt import SEED_SEQUENCE
    assert set(SEED_SEQUENCE) <= cats
    signup = date(2026, 11, 1)
    a = get_daily_prompt("user-a", signup, use_llm=False, signup_date=signup)
    b = get_daily_prompt("user-a", signup, use_llm=False, signup_date=signup)
    assert a["topic"] == b["topic"]


# ---- 端点级：注册天数换算（北京日期口径）----

def _register(client, username):
    r = client.post("/api/v1/auth/register", json={
        "username": username, "password": "Test123456!",
        "name": username, "role": "elderly",
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_daily_prompt_endpoint_seed_day_zero(client, db_session):
    """刚注册的用户：注册当天 seed_day=0，题目落在 person 类"""
    headers = _register(client, "seed_user1")
    r = client.get("/api/v1/training/daily-prompt", headers=headers)
    assert r.status_code == 200
    p = r.json()
    assert p["seed_day"] == 0
    assert p["category"] == "person"


def test_daily_prompt_endpoint_out_of_window(client, db_session):
    """注册满 8 天：出种子窗口，seed_day 为 None"""
    from datetime import datetime, timedelta, timezone as tz
    headers = _register(client, "seed_user2")
    u = db_session.query(app_models.User).filter(
        app_models.User.username == "seed_user2").first()
    u.created_at = datetime.now(tz.utc) - timedelta(days=8)
    db_session.commit()
    r = client.get("/api/v1/training/daily-prompt", headers=headers)
    assert r.status_code == 200
    assert r.json()["seed_day"] is None
