"""记忆衰退分析服务测试"""
from datetime import datetime, timedelta, timezone

from app.models import Session as DBSession, User
from app.services.decline import (
    analyze_narrative_diff,
    build_entity_timeline,
    _split_sentences,
    _avg_sentence_len,
    _entity_density,
    _detect_forgotten_entities,
    _detect_narrative_simplification,
    _detect_repetition,
    _detect_anonymization_trend,
    _compute_decline_score,
    _collect_session_stats,
)


# ============ 工具函数 ============

def _make_user(db, phone="13900000000"):
    """创建一个测试用户"""
    user = User(
        phone=phone,
        hashed_password="x",
        role="elderly",
        name="测试",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_session(db, user_id, text, days_ago, day_number=1):
    """在指定天数前插入一条会话"""
    s = DBSession(
        user_id=user_id,
        day_number=day_number,
        narrative=text,
        graph={"nodes": [], "edges": []},
        metrics={},
        health_score=80,
        anomalies=[],
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(s)
    db.commit()
    return s


# ============ 基础工具函数 ============

def test_split_sentences():
    """切句应过滤空串并按标点分割"""
    text = "今天去公园。然后买菜！回家做饭"
    sents = _split_sentences(text)
    assert len(sents) == 3
    assert sents[0] == "今天去公园"
    assert sents[2] == "回家做饭"


def test_split_sentences_empty():
    """空文本应返回空列表"""
    assert _split_sentences("") == []
    assert _split_sentences(None) == []


def test_avg_sentence_len():
    """平均句子长度按字符数计算"""
    text = "今天去公园。然后买菜"
    # 5 + 4 = 9，2 句，平均 4.5
    assert _avg_sentence_len(text) == 4.5


def test_entity_density():
    """实体密度 = 实体数 * 100 / 文本长度"""
    entities = {"persons": ["老张"], "places": ["公园"], "events": [], "items": []}
    text = "今天在公园碰见老张"  # 9 字
    # 2 个实体 * 100 / 9 ≈ 22.22
    assert _entity_density(text, entities) == 200.0 / 9.0


# ============ 维度检测 ============

def test_forgotten_entities():
    """之前出现但近期未出现的实体应被识别为遗忘"""
    prev = {"entity_freq": {"老张": 3, "公园": 5, "买菜": 2}}
    recent = {"entity_freq": {"公园": 1}}
    forgotten = _detect_forgotten_entities(recent, prev, recent_window_days=7)
    names = [f["entity"] for f in forgotten]
    assert "老张" in names
    assert "买菜" in names
    assert "公园" not in names
    # 按历史出现次数降序
    assert forgotten[0]["previous_count"] >= forgotten[1]["previous_count"]


def test_narrative_simplification_drop():
    """句子长度和实体密度下降应被检测为正向 drop"""
    prev = {"avg_sentence_len": 20.0, "avg_entity_density": 10.0}
    recent = {"avg_sentence_len": 10.0, "avg_entity_density": 5.0}
    result = _detect_narrative_simplification(recent, prev)
    assert result["sentence_len_drop"] > 0
    assert result["entity_density_drop"] > 0
    # 下降了一半，drop 应接近 0.5
    assert 0.4 < result["sentence_len_drop"] < 0.6


def test_narrative_simplification_no_data():
    """历史或近期任一为 0 时不应抛错"""
    prev = {"avg_sentence_len": 0.0, "avg_entity_density": 0.0}
    recent = {"avg_sentence_len": 10.0, "avg_entity_density": 5.0}
    result = _detect_narrative_simplification(recent, prev)
    assert result["sentence_len_drop"] == 0.0


def test_repetition_detection():
    """同一事件在 3 个以上会话日出现应被识别为重复"""
    recent = {
        "per_day_events": [
            {"买菜"}, {"买菜", "散步"}, {"买菜"}, {"做饭"}
        ]
    }
    rep = _detect_repetition(recent, threshold=3)
    events = [r["event"] for r in rep]
    assert "买菜" in events
    assert "做饭" not in events


def test_repetition_below_threshold():
    """低于阈值不应被报告"""
    recent = {"per_day_events": [{"买菜"}, {"散步"}, {"做饭"}]}
    assert _detect_repetition(recent, threshold=3) == []


def test_anonymization_trend_rise():
    """匿名比例上升应产生正 rise"""
    prev = {"anon_ratio": 0.1}
    recent = {"anon_ratio": 0.4}
    result = _detect_anonymization_trend(recent, prev)
    assert result["rise"] > 0
    assert result["rise_pct"] > 0


def test_decline_score_normal():
    """无任何衰退信号时分数应为 0、等级正常"""
    score, level = _compute_decline_score(
        forgotten=[],
        simplification={"sentence_len_drop": 0, "entity_density_drop": 0},
        repetition=[],
        anon_trend={"rise_pct": 0},
    )
    assert score == 0
    assert level == "正常"


def test_decline_score_warning():
    """多维度显著恶化时应进入警告等级"""
    forgotten = [{"entity": "老张", "previous_count": 3, "days_absent": 7}] * 5
    simplification = {"sentence_len_drop": 0.6, "entity_density_drop": 0.5}
    repetition = [{"event": "买菜", "consecutive_days": 5}]
    anon_trend = {"rise_pct": 0.8}
    score, level = _compute_decline_score(forgotten, simplification, repetition, anon_trend)
    assert score >= 50
    assert level == "警告"


# ============ 集成：analyze_narrative_diff ============

def test_analyze_insufficient_data(client, auth_headers):
    """数据不足时应返回 decline_score=0、level=数据不足"""
    r = client.get("/api/v1/decline/analysis", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert data["decline_score"] == 0
    assert data["level"] == "数据不足"
    assert data["forgotten_entities"] == []


def test_analyze_with_history(client, auth_headers, db_session):
    """有历史和近期数据时应返回有效分析"""
    # 直接通过 ORM 插入会话，绕过 NLP 管线以控制时间戳
    from app.routers.auth import get_current_user
    from app.models import User

    user = db_session.query(User).filter_by(phone="13800000000").first()

    # 历史窗口（8~14 天前）：丰富的叙事
    _make_session(
        db_session, user.id,
        "今天在公园碰见老张，我们一起打太极，然后去超市买菜，回家做饭。",
        days_ago=10, day_number=1,
    )
    _make_session(
        db_session, user.id,
        "早上和老伴去医院看张医生，量了血压，然后去药店买药。",
        days_ago=9, day_number=2,
    )
    # 近期窗口（1~6 天前）：简化叙事，老张/张医生消失
    _make_session(
        db_session, user.id,
        "今天买菜。",
        days_ago=5, day_number=3,
    )
    _make_session(
        db_session, user.id,
        "今天买菜。",
        days_ago=4, day_number=4,
    )
    _make_session(
        db_session, user.id,
        "今天买菜。",
        days_ago=3, day_number=5,
    )

    r = client.get("/api/v1/decline/analysis?window_days=7", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert data["level"] in ("正常", "关注", "警告")
    assert 0 <= data["decline_score"] <= 100
    # 老张、张医生应出现在遗忘实体列表里
    forgotten_names = [e["entity"] for e in data["forgotten_entities"]]
    assert "老张" in forgotten_names
    # 买菜应被识别为重复叙述
    rep_events = [e["event"] for e in data["repetition"]]
    assert "买菜" in rep_events


def test_analyze_no_decline(client, auth_headers, db_session):
    """近期叙事与历史保持一致时分数应较低"""
    from app.models import User
    user = db_session.query(User).filter_by(phone="13800000000").first()

    rich_text = "今天在公园碰见老张，我们一起打太极，然后去超市买菜，回家做饭。"
    for days_ago in (10, 9, 8, 6, 5, 4):
        _make_session(db_session, user.id, rich_text, days_ago=days_ago, day_number=1)

    r = client.get("/api/v1/decline/analysis?window_days=7", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    # 实体覆盖一致，不应有遗忘实体
    assert data["forgotten_entities"] == []
    # 分数应处于较低区间
    assert data["decline_score"] < 50


# ============ 集成：build_entity_timeline ============

def test_timeline_basic(client, auth_headers, db_session):
    """时间线应返回每日实体计数和消失实体"""
    from app.models import User
    user = db_session.query(User).filter_by(phone="13800000000").first()

    _make_session(db_session, user.id, "今天和老张在公园打太极", days_ago=20, day_number=1)
    _make_session(db_session, user.id, "今天和老张在公园打太极", days_ago=15, day_number=2)
    _make_session(db_session, user.id, "今天去超市买菜", days_ago=2, day_number=3)

    r = client.get("/api/v1/decline/timeline?days=30", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert "timeline" in data
    assert "disappearing" in data
    assert len(data["timeline"]) == 3
    # 老张、公园、打太极应在消失列表里（最近 7 天未出现）
    disappearing_names = [d["entity"] for d in data["disappearing"]]
    assert "老张" in disappearing_names
    assert "公园" in disappearing_names


def test_timeline_empty(client, auth_headers):
    """无会话时应返回空时间线"""
    r = client.get("/api/v1/decline/timeline?days=30", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert data["timeline"] == []
    assert data["disappearing"] == []
    assert data["total_entities"] == 0
