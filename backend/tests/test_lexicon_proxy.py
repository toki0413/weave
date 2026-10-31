"""W2 词典代维护回归：家属加的词必须落在老人名下，且中文类型名可用

关键语义：转写发生在老人上传时，只有老人 user_id 下的词条会被 stt.py 取去
进百炼 system context。家属写进自己名下 = 对老人的转写零作用。
"""
import uuid

from app.models import CustomLexicon, FamilyLink, User

PHONE = [13900002000]


def _next_phone():
    PHONE[0] += 1
    return str(PHONE[0])


def _register(client, db, role, name):
    phone = _next_phone()
    r = client.post("/api/v1/auth/register",
                    json={"phone": phone, "password": "Test123456!", "role": role, "name": name})
    assert r.status_code == 200, r.text
    user = db.query(User).filter(User.phone == phone).first()
    return user, {"Authorization": "Bearer " + r.json()["access_token"]}


def _link(db, elderly, family):
    db.add(FamilyLink(elderly_user_id=elderly.id, family_user_id=family.id, relation="子女"))
    db.commit()


def test_family_word_lands_on_elder_user_id(client, db_session):
    """核心断言：家属代维护 → 词条 user_id 是老人，不是家属"""
    elder, _ = _register(client, db_session, "elderly", "秀兰")
    fam, fh = _register(client, db_session, "family", "建国")
    _link(db_session, elder, fam)

    r = client.post(f"/api/v1/lexicon/?elderly_id={elder.id}", headers=fh,
                    json={"word": "小宝", "word_type": "person"})
    assert r.status_code == 200, r.text
    row = db_session.query(CustomLexicon).filter(CustomLexicon.id == r.json()["id"]).first()
    assert row is not None
    assert row.user_id == elder.id, "词条必须落在老人名下，否则对老人的转写毫无作用"
    assert row.user_id != fam.id


def test_elder_sees_family_added_word_without_param(client, db_session):
    """老人本人不传 elderly_id → 看得到家属帮忙加的词（同一份词典）"""
    elder, eh = _register(client, db_session, "elderly", "秀兰B")
    fam, fh = _register(client, db_session, "family", "建国B")
    _link(db_session, elder, fam)
    client.post(f"/api/v1/lexicon/?elderly_id={elder.id}", headers=fh,
                json={"word": "公园", "word_type": "place"})

    r = client.get("/api/v1/lexicon/", headers=eh)
    assert r.status_code == 200
    assert any(w["word"] == "公园" for w in r.json()), f"老人看不到家属加的词：{r.json()}"


def test_chinese_word_type_is_normalized(client, auth_headers):
    """中文类型名（人名/地点/事件/物品）在 schema 归一为英文枚举值"""
    for zh, en in [("人名", "person"), ("地点", "place"), ("事件", "event"), ("物品", "item")]:
        r = client.post("/api/v1/lexicon/", headers=auth_headers["headers"],
                        json={"word": f"测试词{zh}", "word_type": zh})
        assert r.status_code == 200, r.text
        assert r.json()["word_type"] == en, f"{zh} 应归一为 {en}，实得 {r.json()['word_type']}"


def test_invalid_word_type_rejected(client, auth_headers):
    """非法类型仍被拒（放宽 pattern 不等于放弃校验）"""
    r = client.post("/api/v1/lexicon/", headers=auth_headers["headers"],
                    json={"word": "怪词", "word_type": "动物"})
    assert r.status_code == 422, f"非法类型应 422，实得 {r.status_code}"


def test_family_cannot_write_for_unlinked_elder(client, db_session):
    """猜 id 代维护别人家的词典 → 403"""
    elder_a, _ = _register(client, db_session, "elderly", "被绑老人C")
    elder_b, _ = _register(client, db_session, "elderly", "陌生老人C")
    fam, fh = _register(client, db_session, "family", "家属C")
    _link(db_session, elder_a, fam)

    r = client.post(f"/api/v1/lexicon/?elderly_id={elder_b.id}", headers=fh,
                    json={"word": "越权词", "word_type": "person"})
    assert r.status_code == 403, f"应 403，实得 {r.status_code}: {r.text[:120]}"
    assert db_session.query(CustomLexicon).filter(
        CustomLexicon.word == "越权词").first() is None, "403 之前不得已经写库"


def test_family_default_target_is_first_link(client, db_session):
    """家属不传 elderly_id → 默认代维护首个绑定老人（与 /decline 同一规则）"""
    elder, _ = _register(client, db_session, "elderly", "默认目标")
    fam, fh = _register(client, db_session, "family", "默认家属")
    _link(db_session, elder, fam)

    r = client.get("/api/v1/lexicon/", headers=fh)
    assert r.status_code == 200
    r2 = client.post("/api/v1/lexicon/", headers=fh, json={"word": "默认词", "word_type": "person"})
    assert r2.status_code == 200
    row = db_session.query(CustomLexicon).filter(CustomLexicon.id == r2.json()["id"]).first()
    assert row.user_id == elder.id
