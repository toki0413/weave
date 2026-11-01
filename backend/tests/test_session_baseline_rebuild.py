"""第 8 条会话的回归：create_session 的个人基线重建分支必须真的可执行。

背景：build_personal_baseline 在 session.py 里被调用却从未导入（自初始提交
946a9a8 起），历史 ≥7 条时第 8 次创建必 500。既有 281 条测试全绿却漏了它，
因为没有任何测试通过 API 创建过 ≥8 条会话——13 周端到端演练才暴露。
本文件就是那条缺失的守护。
"""
import pytest

PHONE_SEQ = [1352000]


@pytest.fixture()
def headers(client):
    PHONE_SEQ[0] += 1
    r = client.post("/api/v1/auth/register", json={
        "phone": str(PHONE_SEQ[0]) + "1", "password": "Test123456!",
        "role": "elderly", "name": "八条门槛"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


TEXTS = [
    "今天和王大爷在公园下棋，聊了两个小时",
    "秀兰陪我去社区医院拿药，回来后做了饭",
    "给儿子打电话，他说周末带孩子来看我",
    "早上去菜市场买了鱼和青菜，摊主认识我",
    "下午在阳台晒太阳，想起以前在纺织厂上班的事",
    "老李来家里串门，一起看了电视里的京剧",
    "跳广场舞的人今天少了一个，听说是搬走了",
    "孙子教我用手机视频，我学会了但记不住步骤",
    "昨天降温，穿了毛衣还是冷，想去医院看看腿",
    "今天在厨房煮面条，盐放多了，想起老伴做的菜",
]


def test_eighth_session_creation_succeeds(client, headers):
    """第 8 条（history_count 达 7 后触发基线重建）不得 500"""
    for i, t in enumerate(TEXTS[:8]):
        r = client.post("/api/v1/session/", headers=headers,
                        json={"day_number": i + 1, "narrative_input": {"text": t}})
        assert r.status_code == 200, f"第 {i + 1} 条创建失败：{r.status_code} {r.text[:200]}"


def test_baseline_rebuild_populates_after_threshold(client, headers):
    """过门槛后新会话的 metrics 应带上个人基线（说明重建分支真的跑通了）"""
    for i, t in enumerate(TEXTS[:9]):
        r = client.post("/api/v1/session/", headers=headers,
                        json={"day_number": i + 1, "narrative_input": {"text": t}})
        assert r.status_code == 200, f"第 {i + 1} 条失败：{r.status_code} {r.text[:200]}"
        body = r.json()

    metrics = body.get("metrics") or {}
    # 基线存在与否取决于样本标准差是否为 0，但字段本身必须在（重建被调用过）
    assert "baseline" in metrics, f"第 9 条未走基线重建：metrics 键={list(metrics)}"
    base = metrics.get("baseline") or {}
    assert "personal_mean" in base or base == {}, f"基线结构异常：{base}"


def test_ten_sessions_stable(client, headers):
    """一路创到 10 条，确认不是只在第 8 条修好、后面又崩"""
    for i, t in enumerate(TEXTS):
        r = client.post("/api/v1/session/", headers=headers,
                        json={"day_number": i + 1, "narrative_input": {"text": t}})
        assert r.status_code == 200, f"第 {i + 1} 条失败：{r.status_code} {r.text[:200]}"
