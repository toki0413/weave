"""认知量表相关接口测试"""
from app.services.scales import SCALES


def test_list_scales(client, auth_headers):
    """获取量表列表应返回 MMSE 和 AD8"""
    r = client.get("/api/v1/scale/", headers=auth_headers["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    ids = [s["id"] for s in data]
    assert "mmse" in ids
    assert "ad8" in ids
    # 列表项应包含基本字段
    mmse = [s for s in data if s["id"] == "mmse"][0]
    assert mmse["total_score"] == 30
    assert mmse["question_count"] == len(SCALES["mmse"]["questions"])


def test_get_scale_detail(client, auth_headers):
    """获取 MMSE 量表详情应包含所有问题"""
    r = client.get("/api/v1/scale/mmse", headers=auth_headers["headers"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"] == "mmse"
    assert data["total_score"] == 30
    assert len(data["questions"]) > 0
    # 每题应包含 id / text / dimension / max_score
    q = data["questions"][0]
    assert "id" in q
    assert "text" in q
    assert "dimension" in q
    assert "max_score" in q


def test_get_scale_not_found(client, auth_headers):
    """不存在的量表应返回 404"""
    r = client.get("/api/v1/scale/nonexistent", headers=auth_headers["headers"])
    assert r.status_code == 404


def test_submit_mmse_normal(client, auth_headers):
    """提交满分 MMSE 应解读为正常"""
    scale = SCALES["mmse"]
    answers = [{"question_id": q["id"], "score": q["max_score"]} for q in scale["questions"]]
    r = client.post("/api/v1/scale/mmse/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_score"] == 30
    assert data["interpretation"] == "正常"


def test_submit_mmse_severe(client, auth_headers):
    """提交零分 MMSE 应解读为重度认知障碍"""
    scale = SCALES["mmse"]
    answers = [{"question_id": q["id"], "score": 0} for q in scale["questions"]]
    r = client.post("/api/v1/scale/mmse/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_score"] == 0
    assert data["interpretation"] == "重度认知障碍"


def test_submit_mmse_moderate(client, auth_headers):
    """提交 20 分 MMSE 应解读为中度认知障碍"""
    scale = SCALES["mmse"]
    # 给前几题满分，凑到 20 分左右
    answers = []
    accumulated = 0
    target = 20
    for q in scale["questions"]:
        remaining = target - accumulated
        if remaining >= q["max_score"]:
            score = q["max_score"]
        elif remaining > 0:
            score = remaining
        else:
            score = 0
        answers.append({"question_id": q["id"], "score": score})
        accumulated += score
    r = client.post("/api/v1/scale/mmse/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_score"] == 20
    assert data["interpretation"] == "中度认知障碍"


def test_submit_ad8_normal(client, auth_headers):
    """提交 0 分 AD8 应解读为正常"""
    scale = SCALES["ad8"]
    answers = [{"question_id": q["id"], "score": 0} for q in scale["questions"]]
    r = client.post("/api/v1/scale/ad8/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_score"] == 0
    assert data["interpretation"] == "正常"


def test_submit_ad8_needs_eval(client, auth_headers):
    """提交 2 分以上 AD8 应提示需进一步评估"""
    scale = SCALES["ad8"]
    # 第一题给 2 分，其余 0 分
    answers = []
    for i, q in enumerate(scale["questions"]):
        answers.append({"question_id": q["id"], "score": 2 if i == 0 else 0})
    r = client.post("/api/v1/scale/ad8/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_score"] == 2
    assert data["interpretation"] == "需进一步评估"


def test_submit_wrong_answer_count(client, auth_headers):
    """答题数量不匹配应返回 400"""
    r = client.post("/api/v1/scale/mmse/submit", headers=auth_headers["headers"], json={"answers": []})
    assert r.status_code == 400


def test_submit_score_out_of_range(client, auth_headers):
    """分数超出范围应返回 400"""
    scale = SCALES["ad8"]
    answers = [{"question_id": q["id"], "score": 5} for q in scale["questions"]]
    r = client.post("/api/v1/scale/ad8/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 400


def test_submit_requires_auth(client):
    """未认证提交应返回 401"""
    r = client.post("/api/v1/scale/mmse/submit", json={"answers": []})
    assert r.status_code == 401


def test_scale_history(client, auth_headers):
    """提交后应能在历史记录中查到"""
    scale = SCALES["ad8"]
    answers = [{"question_id": q["id"], "score": 0} for q in scale["questions"]]
    r = client.post("/api/v1/scale/ad8/submit", headers=auth_headers["headers"], json={"answers": answers})
    assert r.status_code == 200

    r = client.get("/api/v1/scale/history/all", headers=auth_headers["headers"])
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["scale_type"] == "ad8"
