"""NLP 解析测试"""
from app.services.nlp import parse_narrative, check_anomalies, extract_anon_features


def test_parse_narrative_basic():
    """基本解析：返回结构完整，无识别实体也不报错"""
    text = "今天天气不错"
    result = parse_narrative(text)
    assert "entities" in result
    assert "relations" in result
    assert "anomalies" in result
    assert "tokens" in result
    # 没有词典里的词，四类都该是空
    assert result["entities"]["persons"] == []
    assert result["entities"]["places"] == []
    assert result["entities"]["events"] == []


def test_parse_with_person_place():
    """能从叙述中抽出人物、地点、事件"""
    text = "今天和老伴去公园散步"
    result = parse_narrative(text)
    ents = result["entities"]
    assert "老伴" in ents["persons"]
    assert "公园" in ents["places"]
    assert "散步" in ents["events"]
    # 关系里应包含涉及老伴和散步的边（可能在 from 或 to 中）
    all_ends = [r["from"] for r in result["relations"]] + [r["to"] for r in result["relations"]]
    assert any("老伴" in e for e in all_ends)
    assert any("散步" in e for e in all_ends)


def test_parse_anomaly_detection():
    """事件与地点不匹配时应报异常"""
    # 散步期望出现在公园/广场/院子/门口，这里给了医院
    text = "今天去医院散步"
    result = parse_narrative(text)
    assert len(result["anomalies"]) >= 1
    anom = result["anomalies"][0]
    assert anom["event"] == "散步"
    assert anom["type"] == "event-place-mismatch"


def test_parse_relations_structure():
    """关系结构应包含 from/to/type 三个字段"""
    text = "老张在公园打太极"
    result = parse_narrative(text)
    for rel in result["relations"]:
        assert "from" in rel
        assert "to" in rel
        assert "type" in rel


def test_parse_time_anomaly():
    """事件-时间不匹配应报异常：凌晨打太极"""
    text = "凌晨去打太极"
    result = parse_narrative(text)
    time_anomalies = [a for a in result["anomalies"] if a["type"] == "event-time-mismatch"]
    assert len(time_anomalies) >= 1
    assert time_anomalies[0]["event"] == "打太极"
    assert "凌晨" in time_anomalies[0]["unexpected_times"]


def test_parse_time_normal():
    """事件-时间匹配不应报异常：早上打太极"""
    text = "早上去打太极"
    result = parse_narrative(text)
    time_anomalies = [a for a in result["anomalies"] if a["type"] == "event-time-mismatch"]
    assert len(time_anomalies) == 0


def test_parse_anon_features():
    """匿名节点特征提取：那个...的"""
    text = "那个穿红衣服的"
    features = extract_anon_features(text)
    assert len(features) > 0
    assert any("红衣服" in f for f in features)


def test_parse_relation_he_companion():
    """关系提取：和老伴一起"""
    text = "今天和老伴一起散步"
    result = parse_narrative(text)
    all_ends = [r["from"] for r in result["relations"]] + [r["to"] for r in result["relations"]]
    assert any("老伴" in e for e in all_ends)


def test_parse_relation_meet():
    """关系提取：遇到老张"""
    text = "今天遇到老张，"
    result = parse_narrative(text)
    all_ends = [r["from"] for r in result["relations"]] + [r["to"] for r in result["relations"]]
    assert any("老张" in e for e in all_ends)


def test_parse_relation_accompany():
    """关系提取：儿子陪我去医院"""
    text = "儿子陪我去医院看病"
    result = parse_narrative(text)
    all_ends = [r["from"] for r in result["relations"]] + [r["to"] for r in result["relations"]]
    assert any("儿子" in e for e in all_ends)
    assert any("医院" in e for e in all_ends)
