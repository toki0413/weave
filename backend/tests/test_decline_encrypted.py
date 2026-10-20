"""加密会话下的衰退分析回归测试

背景：routers/session.py:146-156 写入时无条件 encrypt() 并置 is_encrypted=True，
而 services/decline.py 的 _collect_session_stats(:70) 与 build_entity_timeline(:362)
都直接 `text = s.narrative or ""`，没有解密。读路径 routers/session.py:219 有
_decrypt_session，decline 侧没有。

现有 test_decline.py 的 _make_session 一律写明文（:42 narrative=text），
所以这条真实写入路径从来没被覆盖过 —— 缺陷因此长期存活。

本文件先用明文构造同一批会话作对照，再构造密文会话，断言两者特征一致。
在缺陷未修前，第二个用例会是红的（密文侧实体密度≈0）。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Session as DBSession, User
from app.services import key_manager as km
from app.services.crypto import encrypt
from app.services.decline import analyze_narrative_diff, build_entity_timeline

USER_SEQ = [0]

PERSONS = ["秀兰", "建国", "德福", "菜市场", "公园", "孙子"]


def _narrative(i):
    return (
        f"今天{PERSONS[i % len(PERSONS)]}陪我去了{PERSONS[(i + 3) % len(PERSONS)]}，"
        f"路上还碰见{PERSONS[(i + 1) % len(PERSONS)]}，我们聊了很久，"
        f"{PERSONS[(i + 4) % len(PERSONS)]}说下周一起去{PERSONS[(i + 5) % len(PERSONS)]}。"
    )


@pytest.fixture
def crypto_key():
    """与线上一致的 32 字节主密钥。"""
    return bytes(range(1, 33))


def _make_user(db, key):
    USER_SEQ[0] += 1
    user = User(username=f"enc_case_user_{USER_SEQ[0]}", hashed_password="x",
                role="elderly", name="测试")
    db.add(user)
    db.commit()
    db.refresh(user)
    km.set_user_key(user.id, key)
    return user


def _seed(db, user_id, key, encrypted, n=6):
    """插入 n 条会话，**均分落到两个窗口**：3 条在最近 7 天、3 条在 7–14 天前。

    早先版本把 6 条都放在最近 7 天内，导致 prev 窗口为空、
    analyze_narrative_diff 在 decline.py:270 直接早退并返回空占位 dict，
    测试断的是"没数据"而不是"读了密文"。
    """
    half = n // 2
    for i in range(n):
        text = _narrative(i)
        if encrypted:
            payload, is_enc = encrypt(text, key), True
        else:
            payload, is_enc = text, False
        days_ago = i if i < half else half + 3 + (i - half) * 2   # 后者落在 7–14 天外
        db.add(DBSession(
            user_id=user_id,
            day_number=i + 1,
            narrative=payload,
            is_encrypted=is_enc,
            graph={"nodes": [], "edges": []},
            metrics={},
            health_score=80,
            anomalies=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        ))
    db.commit()


def test_nlp_extracts_entities_from_plain_text(crypto_key):
    """最直接的一条：明文能被提出实体。不提这个，窗口类断言可能空转。"""
    from app.services.nlp import extract_entities
    ents = extract_entities(_narrative(0))
    total = sum(len(v) for v in ents.values())
    assert total > 0, f"明文提不出实体，测试文本或分词词典有问题：{ents}"


def test_plain_path_has_features(db_session, crypto_key):
    """明文对照：证明测试脚手架本身能产出非零特征，否则后面的对比无意义。"""
    user = _make_user(db_session, crypto_key)
    _seed(db_session, user.id, crypto_key, encrypted=False)

    result = analyze_narrative_diff(user.id, db_session, window_days=7)
    timeline = build_entity_timeline(user.id, db_session, days=30)

    assert result["recent_session_count"] >= 1, "窗口内没取到会话，用例结构有问题"
    assert result["previous_session_count"] >= 1, \
        f"前窗为空（prev={result['previous_session_count']}），会走 decline.py:270 早退，断不到特征"
    assert result.get("narrative_simplification"), "simplification 为空 dict，等于没跑到检测器"
    assert result["narrative_simplification"].get("recent_entity_density", 0) > 0, \
        "明文路径实体密度为 0，测试数据或分词有问题"
    assert timeline["total_entities"] > 0, "明文路径时间线没有实体"


def test_encrypted_sessions_yield_same_features(db_session, crypto_key):
    """密文会话必须与明文得到一致特征。

    缺陷未修时本用例会红：decline 读的是 base64 密文，实体密度与时间线实体数
    都会塌到接近 0，而接口不报错 —— 静默产出无意义数字。
    """
    plain_user = _make_user(db_session, crypto_key)
    _seed(db_session, plain_user.id, crypto_key, encrypted=False)
    plain = analyze_narrative_diff(plain_user.id, db_session, window_days=7)
    plain_tl = build_entity_timeline(plain_user.id, db_session, days=30)

    enc_user = _make_user(db_session, crypto_key)
    _seed(db_session, enc_user.id, crypto_key, encrypted=True)
    enc = analyze_narrative_diff(enc_user.id, db_session, window_days=7)
    enc_tl = build_entity_timeline(enc_user.id, db_session, days=30)

    assert enc["recent_session_count"] == plain["recent_session_count"]

    enc_density = enc["narrative_simplification"].get("recent_entity_density", 0)
    plain_density = plain["narrative_simplification"].get("recent_entity_density", 0)
    assert enc_density > 0, (
        f"密文会话实体密度为 {enc_density}，说明衰退分析在读密文"
    )
    assert abs(enc_density - plain_density) < 1e-6, (
        f"密文/明文特征不一致：enc={enc_density} plain={plain_density}"
    )
    assert enc_tl["total_entities"] == plain_tl["total_entities"]


def test_decrypt_failure_reports_instead_of_falling_back_to_ciphertext(db_session, crypto_key):
    """解不开时必须显式报数据不足，不能静默退回密文继续算。

    这条防"修复走样"：若哪天有人把 decrypt_narrative 改成 except 里 return 原文，
    上面的相等断言可能仍然通过，但缺陷会以另一种形式回来 —— 拿着近乎恒定的
    无意义特征出结论，而且完全不报错。
    """
    user = _make_user(db_session, crypto_key)
    _seed(db_session, user.id, crypto_key, encrypted=True)
    km.clear_user_key(user.id)          # 模拟未登录 / 密钥丢失

    result = analyze_narrative_diff(user.id, db_session, window_days=7)
    assert result["level"] == "数据不足", f"竟然给出了结论：{result['level']}"
    assert result["decrypt_failed"]["recent"] >= 1, "没把解密失败计入 skipped"
    assert result["narrative_simplification"] == {}, "密文被当明文算了特征"

    timeline = build_entity_timeline(user.id, db_session, days=30)
    assert timeline["decrypt_failed"] >= 1
    assert timeline["total_entities"] == 0
