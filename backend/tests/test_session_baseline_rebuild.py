"""第 8 条会话触发个人基线重建（回归测试）

`create_session` 在 `history_count >= 7` 时调用 `build_personal_baseline`，
但该函数从未导入——`NameError` 由 FastAPI 转成 500。试点按每天 3 条记录，
第 3 天必然触发，且此前的测试从未创建过 8 条会话，所以全量测试全绿掩盖了它。

本文件锁定两条事实：第 8 条及之后的会话不再 500；重建分支确实被走到。
"""
import pytest


def _post_session(client, headers, day, text=None):
    return client.post(
        "/api/v1/session/",
        json={
            "narrative_input": {"text": text or f"今天第{day}天，天气不错，和老朋友聊了会天。"},
            "day_number": day,
        },
        headers=headers,
    )


def test_eighth_session_does_not_500(client, auth_headers):
    """前 7 条走普通分支，第 8 条进入个人基线重建分支（历史缺陷点）"""
    headers = auth_headers["headers"]
    statuses = []
    for day in range(1, 9):
        statuses.append(_post_session(client, headers, day).status_code)

    assert statuses[:7] == [200] * 7, f"前 7 条会话异常: {statuses[:7]}"
    assert statuses[7] == 200, (
        f"第 8 条会话（个人基线重建分支）返回 {statuses[7]}，"
        "通常是 build_personal_baseline 未导入或重建逻辑抛错"
    )


def test_sessions_stay_healthy_beyond_threshold(client, auth_headers):
    """阈值之后继续写入，确认不是只在第 8 条偶然通过"""
    headers = auth_headers["headers"]
    for day in range(1, 12):
        r = _post_session(client, headers, day)
        assert r.status_code == 200, f"第 {day} 条会话失败: {r.status_code} {r.text[:200]}"
        assert r.json()["day_number"] == day


def test_baseline_row_written_after_rebuild(client, auth_headers, db_session):
    """重建分支不仅不报错，还应落一条无 session_id 的个人基线"""
    from app.models import Baseline

    headers = auth_headers["headers"]
    for day in range(1, 9):
        assert _post_session(client, headers, day).status_code == 200

    row = (
        db_session.query(Baseline)
        .filter(Baseline.session_id.is_(None))
        .first()
    )
    assert row is not None, "第 8 条会话后应存在个人基线行"
    assert row.personal_mean, "个人基线应写入均值"
