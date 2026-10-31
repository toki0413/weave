"""W0 回归：/decline/analysis 与 /timeline 的分析对象与权限

缺陷背景：两端点此前只分析 current_user.id —— 家属账号打开家属端 tier 卡，
跑的是家属自己的空数据，永远显示"记录还不够"，老人录满四周也一样。
用户一律经 API 注册（注册会缓存主密钥，直接建 DB 行会导致会话加密 401）。
"""
from app.models import FamilyLink, User

PHONE = [13900001000]


def _next_phone():
    PHONE[0] += 1
    return str(PHONE[0])


def _register(client, db, role, name):
    """注册并登录，返回 (User, headers)"""
    phone = _next_phone()
    r = client.post("/api/v1/auth/register",
                    json={"phone": phone, "password": "Test123456!", "role": role, "name": name})
    assert r.status_code == 200, r.text
    user = db.query(User).filter(User.phone == phone).first()
    assert user is not None, f"注册成功但查不到用户 {phone}"
    return user, {"Authorization": "Bearer " + r.json()["access_token"]}


def _link(db, elderly, family):
    db.add(FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id, relation="子女"))
    db.commit()


def _sessions(client, headers, texts):
    for i, t in enumerate(texts):
        r = client.post("/api/v1/session/", headers=headers,
                        json={"day_number": i + 1, "narrative_input": {"text": t}})
        assert r.status_code == 200, r.text


def test_family_defaults_to_linked_elder(client, db_session):
    """已绑定家属不传 elderly_id → 拿到老人的分析，而不是自己的空数据"""
    elder, eh = _register(client, db_session, "elderly", "秀兰")
    fam, fh = _register(client, db_session, "family", "建国")
    _link(db_session, elder, fam)
    _sessions(client, eh, [
        "今天和老王在下棋，然后回家做饭",
        "秀兰陪我去社区医院拿药，路上买了菜",
        "给孙子打电话，他说周末回来看我",
    ])

    r_elder = client.get("/api/v1/decline/analysis?window_days=7", headers=eh)
    r_fam = client.get("/api/v1/decline/analysis?window_days=7", headers=fh)
    assert r_elder.status_code == 200 and r_fam.status_code == 200

    n_elder = r_elder.json()["recent_session_count"]
    n_fam = r_fam.json()["recent_session_count"]
    assert n_elder == 3, f"老人自己的会话数应为 3，实得 {n_elder}（测试前提不成立）"
    assert n_fam == n_elder, (
        f"家属默认应解析到绑定的老人（{n_elder}），实得 {n_fam} —— 0 即缺陷复发")

    body = r_fam.json()
    for key in ("tier", "tier_signals", "next_step"):
        assert key in body, f"响应缺 {key}，家属端 tier 卡无数据可用"

    # timeline 同规则
    r_tl = client.get("/api/v1/decline/timeline?days=30", headers=fh)
    assert r_tl.status_code == 200
    assert r_tl.json() == client.get("/api/v1/decline/timeline?days=30", headers=eh).json()


def test_family_can_target_explicitly_bound_elder(client, db_session):
    """多老人场景：显式传 elderly_id 指定对象，结果与默认(首个)可区分"""
    elder_a, _ = _register(client, db_session, "elderly", "老人A")
    elder_b, bh = _register(client, db_session, "elderly", "老人B")
    fam, fh = _register(client, db_session, "family", "家属")
    _link(db_session, elder_a, fam)
    _link(db_session, elder_b, fam)
    _sessions(client, bh, ["老人B的独有叙述，去了公园"])

    r_b = client.get(f"/api/v1/decline/analysis?window_days=7&elderly_id={elder_b.id}", headers=fh)
    assert r_b.status_code == 200
    assert r_b.json()["recent_session_count"] == 1


def test_family_forbidden_for_unlinked_elder(client, db_session):
    """猜 id 越权必须 403——修之前任何人传 id 都会被无声忽略"""
    elder_a, _ = _register(client, db_session, "elderly", "被绑老人")
    elder_b, _ = _register(client, db_session, "elderly", "陌生老人")
    fam, fh = _register(client, db_session, "family", "家属")
    _link(db_session, elder_a, fam)

    r = client.get(f"/api/v1/decline/analysis?window_days=7&elderly_id={elder_b.id}", headers=fh)
    assert r.status_code == 403, f"越权应 403，实得 {r.status_code}: {r.text[:120]}"


def test_family_without_link_gets_404(client, db_session):
    """未绑定家属 → 404 明说"尚未绑定"，而不是静默返回自己的空分析"""
    fam, fh = _register(client, db_session, "family", "无绑定家属")
    r = client.get("/api/v1/decline/analysis?window_days=7", headers=fh)
    assert r.status_code == 404, r.text
    assert "尚未绑定" in r.json()["detail"]


def test_elderly_self_behavior_unchanged(client, db_session):
    """老人本人不传 id → 仍分析自己，且不受新默认逻辑影响（向后兼容）"""
    elder, eh = _register(client, db_session, "elderly", "本人")
    r = client.get("/api/v1/decline/analysis?window_days=7", headers=eh)
    assert r.status_code == 200, r.text
    assert r.json()["recent_session_count"] == 0
