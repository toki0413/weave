"""B-2 端到端演练：13 周合成数据喂进真实链路，验证 tier 引擎的输出分布与能力边界。

不依赖外部密钥，走完整链路：注册 → create_session（含加密与 NLP）→ 周基线
→ tier 评估 → /decline/analysis 响应。

三条被实跑证实的结论（另有两处先验被否证，见各测试 docstring）：
1. 链路能攒出有效周：valid_weeks=13 / baseline_weeks=12 / max_attainable_z=3.175
   （与 (n-1)/√n 在 n=12 时的理论值一致）
2. 平稳数据不误报（green），阶跃式与渐进式衰退均被检出（red / amber）
3. low_confidence 三态语义（True / False / NULL）在真实写入路径上成立

**遗留的标定疑问（未修，需真实数据）**：step 剧本里 audio 类信号算出
|z| = 17.5 ~ 26.97，远超引擎自报的 max_attainable_z=3.175——因为基线 std
很小时 z 会爆表。这既可能"真的该报"（说话量骤减本就是强信号），也可能是
分母退化造成的过度自信。曾试加变异系数下限（min_cv=0.08），结果连平稳剧本
都因可投票维度不足退化成 insufficient_data，遂撤回：判定语义不该由合成数据
拍板，留作试点期用真实分布标定。此处仅以断言锁定"能检出"，不锁 z 的幅度。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text

from app.models import Session as DBSession

WEEKS = 13
PER_WEEK = 3
UTC = timezone.utc
LOCAL_OFFSET = timedelta(minutes=480)      # 与 weekly_baseline 的北京时区一致

_PHONE_SEQ = [1353000]
POOL = ["秀兰", "建国", "老王", "社区医院", "公园", "菜市场", "儿子", "孙子", "老李", "纺织厂"]


def _local_today():
    return (datetime.now(UTC) + LOCAL_OFFSET).date()


def _week_dates(weeks_back):
    """该周可放的本地日期（周一/二/三），未来日期自动丢弃。"""
    today = _local_today()
    monday = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks_back)
    return [monday + timedelta(days=i) for i in range(PER_WEEK)
            if monday + timedelta(days=i) <= today]


def _narrative(week_back, idx, pattern):
    """pattern: stable | drift（13 周线性变差）| step（仅本周骤变）"""
    progress = (WEEKS - 1 - week_back) / (WEEKS - 1)      # 0=最早周 1=本周
    if pattern == "stable":
        n_sent, n_ent, degrade = 6, 5, False
    elif pattern == "drift":
        n_sent = max(2, int(6 - 4 * progress))
        n_ent = max(1, int(5 - 4 * progress))
        degrade = progress > 0.85
    else:                                                   # step
        n_sent, n_ent = (2, 1) if week_back == 0 else (6, 5)
        degrade = week_back == 0
    bits = []
    for i in range(n_sent):
        if i < n_ent:
            bits.append(f"今天和{POOL[(i + idx) % len(POOL)]}一起做了件事，聊了挺久还约好下次再聚")
        elif degrade:
            bits.append("那个…就是那个人来了，我们说了些事情，那个地方也去了")
        else:
            bits.append("今天在家待着做了饭洗了衣服，没什么特别的事情发生")
    return "。".join(bits) + "。"


def _audio(idx, pattern, week_back):
    """带确定性抖动——常量会让 std=0、该信号变 indeterminate（首轮就踩过）。"""
    base = {"duration_sec": 50.0 + (idx % 9), "speech_ratio": round(0.62 + 0.03 * (idx % 5), 2),
            "pause_count": 3 + (idx % 4), "words_per_minute": 90.0 + 4 * (idx % 6)}
    if pattern == "step" and week_back == 0:
        base.update({"duration_sec": 12.0, "speech_ratio": 0.25,
                     "pause_count": 15, "words_per_minute": 30.0})
    return base


def _seed(client, db, headers, pattern, weeks=WEEKS, low_confidence=False):
    created = 0
    for back in range(weeks - 1, -1, -1):
        for i, day in enumerate(_week_dates(back)):
            r = client.post("/api/v1/session/", headers=headers, json={
                "day_number": created + 1,
                "narrative_input": {"text": _narrative(back, i, pattern)},
                "audio_metrics": _audio(i + back, pattern, back),
                "asr_provider": "vosk" if low_confidence else "bailian",
                "asr_confidence": 0.2 if low_confidence else 0.85,
            })
            assert r.status_code == 200, r.text[:200]
            row = db.get(DBSession, r.json()["id"])
            # UTC 04:00 = 北京 12:00，保证 +480 后仍落在同一本地日与同一周
            row.created_at = datetime(day.year, day.month, day.day, 4, 0, 0)
            db.commit()
            created += 1
    return created


@pytest.fixture()
def elder(client):
    _PHONE_SEQ[0] += 1
    r = client.post("/api/v1/auth/register", json={
        "phone": str(_PHONE_SEQ[0]) + "1", "password": "Test123456!",
        "role": "elderly", "name": "演练老人"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _analysis(client, headers):
    r = client.get("/api/v1/decline/analysis?window_days=7", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_pipeline_builds_12_week_baseline(client, db_session, elder):
    """1. 端到端能攒出 ≥12 个有效周（否则 tier 恒为 insufficient_data）"""
    headers = elder
    n = _seed(client, db_session, headers, "stable")
    body = _analysis(client, headers)
    print("\n[stable] sessions=", n, "valid_weeks=", body.get("valid_weeks"),
          "baseline_weeks=", body.get("baseline_weeks"),
          "max_attainable_z=", body.get("max_attainable_z"), "tier=", body.get("tier"))
    assert n == WEEKS * PER_WEEK
    assert (body.get("valid_weeks") or 0) >= 12
    # n=12 时 z 可达上限 (n-1)/√n ≈ 3.175 —— 引擎自报的统计门槛
    assert abs((body.get("max_attainable_z") or 0) - 3.175) < 0.05


def test_stable_not_flagged(client, db_session, elder):
    """2. 平稳数据不得判危险（假阳方向）"""
    headers = elder
    _seed(client, db_session, headers, "stable")
    body = _analysis(client, headers)
    assert body.get("tier") == "green", f"平稳数据被判 {body.get('tier')}：{body.get('tier_reason')}"


def test_step_degradation_is_detected(client, db_session, elder):
    """3. 相对自身基线的阶跃式偏离必须被检出（真阳方向）"""
    headers = elder
    _seed(client, db_session, headers, "step")
    body = _analysis(client, headers)
    sig = {s.get("name"): s for s in (body.get("tier_signals") or [])}
    print("\n[step] tier=", body.get("tier"), "reason=", body.get("tier_reason"))
    print("[step] signals=", json.dumps(
        {k: (v.get("z_score"), v.get("severity")) for k, v in sig.items()}, ensure_ascii=False))
    assert body.get("tier") in ("amber", "red"), (
        f"阶跃式衰退未检出：tier={body.get('tier')} reason={body.get('tier_reason')}")


def test_gradual_drift_is_detected(client, db_session, elder):
    """4. 13 周线性漂移同样被检出（实测 amber）。

    修正记录：写这个演练时我的假设是"渐进漂移会被个人基线吸收、判 green"，
    实跑否证了它——drift 判 amber（entity_density z≈1.69、avg_sentence_len
    z≈3.11）。因此断言按实测写成"可被检出"。两个方向的断言都由真实运行钉住：
    改判定语义会先撞到这里，而不是靠 README 的说法。
    """
    headers = elder
    _seed(client, db_session, headers, "drift")
    body = _analysis(client, headers)
    sig = {s.get("name"): s for s in (body.get("tier_signals") or [])}
    print("\n[drift] tier=", body.get("tier"),
          "entity_density_z=", (sig.get("entity_density") or {}).get("z_score"),
          "avg_sentence_len_z=", (sig.get("avg_sentence_len") or {}).get("z_score"))
    assert body.get("tier") in ("amber", "red"), (
        f"渐进漂移未被检出（tier={body.get('tier')} reason={body.get('tier_reason')}）"
        f"——若这是有意收紧灵敏度，请连同对外表述一起更新")


def test_low_confidence_three_state(client, db_session, elder):
    """5. 三态语义：0.85→False（已知可信）/ 0.2→True（低置信）/ 不传→NULL（未知）"""
    headers = elder
    n_ok = _seed(client, db_session, headers, "stable", weeks=4)
    n_low = _seed(client, db_session, headers, "stable", weeks=1, low_confidence=True)
    r = client.post("/api/v1/session/", headers=headers,
                    json={"day_number": 99, "narrative_input": {"text": "手动输入的一句话"}})
    assert r.status_code == 200

    db = db_session

    def cnt(expr):
        return db.execute(sa_text(
            "SELECT COUNT(*) FROM sessions WHERE low_confidence IS " + expr)).scalar()

    n_true, n_false, n_null = cnt("1"), cnt("0"), cnt("NULL")
    print("\n[3-state] True=", n_true, "False=", n_false, "NULL=", n_null,
          "| normal=", n_ok, "low=", n_low)
    assert n_true == n_low > 0, "低置信未标 True"
    assert n_false == n_ok, f"正常会话应标 False（应 {n_ok}，实得 {n_false}）"
    assert n_null == 1, f"无 ASR 信息应为 NULL（未知），实得 {n_null}"
