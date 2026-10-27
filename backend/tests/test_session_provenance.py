"""story-8 验收回归：会话创建写入 0018 ASR 溯源列 + day_number 自动计算。

数据合同（PRD pilot-p0-repair）：
- 走过 /stt/transcribe 的会话：asr_provider / asr_confidence / asr_duration_sec 非空，
  low_confidence 按阈值 0.5 判定
- 手动输入/无音频：溯源列保持 NULL（"未知"），绝不编造
- day_number <= 0 为"未指定"哨兵 → 后端按首条会话日起算；显式 >0 透传
"""
from datetime import datetime, timedelta, timezone

from app.models import Session as DBSession


def _post_session(client, headers, text="今天秀兰陪我去公园散步", **extra):
    body = {"narrative_input": {"text": text}}
    body.update(extra)
    return client.post("/api/v1/session/", headers=headers, json=body)


def _latest(db, user_id):
    return (
        db.query(DBSession)
        .filter(DBSession.user_id == user_id)
        .order_by(DBSession.created_at.desc())
        .first()
    )


def test_create_session_writes_asr_provenance(client, auth_headers, db_session):
    r = _post_session(
        client, auth_headers["headers"],
        audio_metrics={"duration_sec": 42.5, "speech_ratio": 0.7, "pause_count": 3, "words_per_minute": 90.0},
        asr_provider="bailian", asr_confidence=0.8, source="daily_prompt",
    )
    assert r.status_code == 200, r.text
    row = _latest(db_session, r.json()["user_id"])
    assert row.asr_provider == "bailian"
    assert row.asr_confidence == 0.8
    assert row.low_confidence is False
    assert row.asr_duration_sec == 42.5
    # 音频指标同时进 metrics.audio（既有契约不回退）
    assert row.metrics.get("audio", {}).get("duration_sec") == 42.5


def test_low_confidence_threshold(client, auth_headers, db_session):
    """0.5 阈值：0.3 → True；0.8 → False；不传 → NULL（不编造）。"""
    h = auth_headers["headers"]
    r1 = _post_session(client, h, text="低置信的会话", asr_provider="vosk", asr_confidence=0.3)
    r2 = _post_session(client, h, text="高置信的会话", asr_provider="bailian", asr_confidence=0.8)
    r3 = _post_session(client, h, text="手动输入的会话")
    assert r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200
    rows = (
        db_session.query(DBSession)
        .filter(DBSession.user_id == r1.json()["user_id"])
        .order_by(DBSession.created_at.asc())
        .all()
    )
    by_text = {s.narrative: s for s in rows}
    # narrative 已加密，按入库顺序对应：r1 → rows[0]，r2 → rows[1]，r3 → rows[2]
    assert rows[0].low_confidence is True and rows[0].asr_provider == "vosk"
    assert rows[1].low_confidence is False
    assert rows[2].asr_provider is None
    assert rows[2].asr_confidence is None
    assert rows[2].low_confidence is None
    assert rows[2].asr_duration_sec is None


def test_day_number_auto_first_session(client, auth_headers):
    """day_number=0 哨兵 → 首条会话即第 1 天。"""
    r = _post_session(client, auth_headers["headers"], day_number=0)
    assert r.status_code == 200, r.text
    assert r.json()["day_number"] == 1


def test_day_number_auto_after_gap(client, auth_headers, db_session):
    """首条会话回拨 6 天后，新会话自动算第 7 天。"""
    r1 = _post_session(client, auth_headers["headers"], text="第一天", day_number=0)
    assert r1.status_code == 200
    row = _latest(db_session, r1.json()["user_id"])
    row.created_at = datetime.now(timezone.utc) - timedelta(days=6)
    db_session.commit()

    r2 = _post_session(client, auth_headers["headers"], text="六天后的回归", day_number=0)
    assert r2.status_code == 200
    assert r2.json()["day_number"] == 7


def test_day_number_explicit_honored(client, auth_headers):
    """显式 >0 的 day_number 照旧透传（full 模式 parse.js 自算、测试 seeding 依赖）。"""
    r = _post_session(client, auth_headers["headers"], day_number=5)
    assert r.status_code == 200
    assert r.json()["day_number"] == 5
