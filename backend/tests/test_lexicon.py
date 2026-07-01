"""自定义词典 CRUD + NLP 集成测试"""
from app.services.nlp import extract_entities, parse_narrative


# ========== 路由 CRUD ==========
def test_list_lexicon_empty(client, auth_headers):
    """新用户词典应为空"""
    r = client.get("/api/v1/lexicon/", headers=auth_headers["headers"])
    assert r.status_code == 200
    assert r.json() == []


def test_add_lexicon_word(client, auth_headers):
    """添加单个词条"""
    r = client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json={
        "word": "小明",
        "word_type": "person",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["word"] == "小明"
    assert data["word_type"] == "person"
    assert "id" in data


def test_add_lexicon_duplicate(client, auth_headers):
    """同词同类型重复添加应被拒绝"""
    body = {"word": "社区医院", "word_type": "place"}
    r1 = client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json=body)
    assert r1.status_code == 200
    r2 = client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json=body)
    assert r2.status_code == 400


def test_add_lexicon_invalid_type(client, auth_headers):
    """非法类型应返回 422"""
    r = client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json={
        "word": "测试",
        "word_type": "unknown",
    })
    assert r.status_code == 422


def test_list_lexicon_with_filter(client, auth_headers):
    """按类型过滤"""
    for w, t in [("小明", "person"), ("社区医院", "place"), ("跳广场舞", "event")]:
        client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json={"word": w, "word_type": t})
    r = client.get("/api/v1/lexicon/?word_type=person", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["word_type"] == "person"


def test_delete_lexicon_word(client, auth_headers):
    """删除词条"""
    r = client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json={
        "word": "老花镜",
        "word_type": "item",
    })
    wid = r.json()["id"]

    r = client.delete(f"/api/v1/lexicon/{wid}", headers=auth_headers["headers"])
    assert r.status_code == 200

    # 再查应该没了
    r = client.get("/api/v1/lexicon/", headers=auth_headers["headers"])
    words = [item["word"] for item in r.json()]
    assert "老花镜" not in words


def test_delete_lexicon_not_found(client, auth_headers):
    """删除不存在的词条返回 404"""
    r = client.delete("/api/v1/lexicon/nonexistent-id", headers=auth_headers["headers"])
    assert r.status_code == 404


def test_import_lexicon(client, auth_headers):
    """批量导入"""
    r = client.post("/api/v1/lexicon/import", headers=auth_headers["headers"], json={
        "items": [
            {"word": "小明", "word_type": "person"},
            {"word": "社区医院", "word_type": "place"},
            {"word": "跳广场舞", "word_type": "event"},
        ]
    })
    assert r.status_code == 200, r.text
    created = r.json()
    assert len(created) == 3

    # 再查应有 3 条
    r = client.get("/api/v1/lexicon/", headers=auth_headers["headers"])
    assert len(r.json()) == 3


def test_import_lexicon_skip_duplicate(client, auth_headers):
    """批量导入应跳过重复项"""
    # 先单独加一条
    client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json={
        "word": "小明", "word_type": "person",
    })
    # 再批量导入，包含重复 + 新词
    r = client.post("/api/v1/lexicon/import", headers=auth_headers["headers"], json={
        "items": [
            {"word": "小明", "word_type": "person"},      # 重复，跳过
            {"word": "小红", "word_type": "person"},      # 新增
            {"word": "社区医院", "word_type": "place"},   # 新增
        ]
    })
    assert r.status_code == 200
    assert len(r.json()) == 2  # 只新增 2 条


def test_lexicon_isolated_between_users(client):
    """不同用户的词典应隔离"""
    # 用户 A
    client.post("/api/v1/auth/register", json={
        "phone": "13900000001", "password": "Test123456!", "name": "A",
    })
    r = client.post("/api/v1/auth/login", json={"phone": "13900000001", "password": "Test123456!"})
    headers_a = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.post("/api/v1/lexicon/", headers=headers_a, json={"word": "用户A的孙子", "word_type": "person"})

    # 用户 B
    client.post("/api/v1/auth/register", json={
        "phone": "13900000002", "password": "Test123456!", "name": "B",
    })
    r = client.post("/api/v1/auth/login", json={"phone": "13900000002", "password": "Test123456!"})
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.post("/api/v1/lexicon/", headers=headers_b, json={"word": "用户B的孙女", "word_type": "person"})

    # A 只能看到自己的
    r = client.get("/api/v1/lexicon/", headers=headers_a)
    words_a = [item["word"] for item in r.json()]
    assert "用户A的孙子" in words_a
    assert "用户B的孙女" not in words_a


def test_lexicon_requires_auth(client):
    """未认证访问应返回 401"""
    r = client.get("/api/v1/lexicon/")
    assert r.status_code == 401


# ========== NLP 集成 ==========
def test_extract_entities_with_custom_words():
    """自定义词应能被识别为对应类型"""
    text = "今天和小明去社区医院跳广场舞"
    custom = [
        {"word": "小明", "type": "person"},
        {"word": "社区医院", "type": "place"},
        {"word": "跳广场舞", "type": "event"},
    ]
    ents = extract_entities(text, custom)
    assert "小明" in ents["persons"]
    assert "社区医院" in ents["places"]
    assert "跳广场舞" in ents["events"]


def test_extract_entities_without_custom_words():
    """不传自定义词典时，行为应与原来一致"""
    text = "今天和老伴去公园散步"
    ents = extract_entities(text)
    assert "老伴" in ents["persons"]
    assert "公园" in ents["places"]
    assert "散步" in ents["events"]


def test_parse_narrative_with_custom_words():
    """完整 NLP 管线应能利用自定义词典"""
    text = "今天小明陪我去社区医院复诊"
    custom = [
        {"word": "小明", "type": "person"},
        {"word": "社区医院", "type": "place"},
    ]
    result = parse_narrative(text, custom)
    ents = result["entities"]
    assert "小明" in ents["persons"]
    assert "社区医院" in ents["places"]
    # 关系里应出现涉及小明的边
    all_ends = [r["from"] for r in result["relations"]] + [r["to"] for r in result["relations"]]
    assert any("小明" in e for e in all_ends)


def test_custom_words_do_not_pollute_global():
    """临时加入的自定义词不应污染后续调用"""
    custom = [{"word": "测试专有名词XYZ", "type": "person"}]
    extract_entities("测试专有名词XYZ来了", custom)
    # 再不传 custom_words 调用，应该识别不到
    ents = extract_entities("测试专有名词XYZ来了")
    assert "测试专有名词XYZ" not in ents["persons"]


# ========== 会话集成 ==========
def test_session_uses_custom_lexicon(client, auth_headers):
    """创建会话时，自定义词典应被加载进 NLP"""
    # 先添加一个自定义人物
    client.post("/api/v1/lexicon/", headers=auth_headers["headers"], json={
        "word": "王大爷",
        "word_type": "person",
    })
    # 用包含该人物的叙述创建会话
    r = client.post("/api/v1/session/", headers=auth_headers["headers"], json={
        "day_number": 1,
        "narrative_input": {"text": "今天和王大爷去公园散步"},
    })
    assert r.status_code == 200, r.text
    graph = r.json()["graph"]
    labels = [n["label"] for n in graph["nodes"]]
    assert "王大爷" in labels
