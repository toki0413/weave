"""/stt/transcribe 认证与词典热词接线测试。

打桩边界（只测 stt.py 这一层：认证 → 查当前用户词典 → 词汇进 provider 链）：
- _convert_to_wav 打桩为直接成功：不依赖 ffmpeg、不产生真实音频。
  _extract_audio_features 对非法/缺失 wav 自带异常兜底，返回零值指标。
- resolve_chain 打桩为返回一个记录 context_words 的假 provider，
  不发网络请求。vosk/百炼各自的真实行为由 test_asr_providers.py 单测覆盖，
  百炼 system message 含词典词的断言也在那边（test_bailian_context_system_message_included）。
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.services.asr_providers import TranscriptionResult


def _fake_provider(captured):
    """记录每次 transcribe 收到的 context_words，返回固定转写文本。"""
    def transcribe(wav_path, context_words, language):
        captured.append({"context_words": list(context_words), "language": language})
        return TranscriptionResult("今天秀兰陪我去公园散步", "fake", "fake-model")
    return SimpleNamespace(name="fake", available=lambda: True, transcribe=transcribe)


def _upload(client, headers):
    return client.post(
        "/api/v1/stt/transcribe",
        headers=headers,
        files={"audio": ("recording.webm", b"\x00\x00", "audio/webm")},
    )


def _login(client, phone, name):
    client.post("/api/v1/auth/register", json={
        "phone": phone, "password": "Test123456!", "name": name})
    r = client.post("/api/v1/auth/login", json={"phone": phone, "password": "Test123456!"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- 认证

def test_transcribe_requires_auth(client):
    """/stt/transcribe 此前无认证（前端一直带 token 而后端不校验），
    现在未登录必须 401 —— 这是接线词典顺手关掉的口子。"""
    r = _upload(client, {})
    assert r.status_code == 401


def test_health_stays_public(client):
    """/stt/health 保持无需认证：部署探活用，不落用户数据。"""
    r = client.get("/api/v1/stt/health")
    assert r.status_code == 200


# ---------------------------------------------------------------- 词典接线

def test_lexicon_words_reach_provider(client, auth_headers):
    """当前用户词典词必须出现在 provider 收到的 context_words 里，
    且 lexicon_hit_rate 按真实词典计算（命中 1/2）。"""
    for w, t in [("秀兰", "person"), ("社区医院", "place")]:
        r = client.post("/api/v1/lexicon/", headers=auth_headers["headers"],
                        json={"word": w, "word_type": t})
        assert r.status_code == 200, r.text

    captured = []
    with patch("app.routers.stt._convert_to_wav", return_value=True), \
         patch("app.routers.stt.resolve_chain", return_value=[_fake_provider(captured)]):
        r = _upload(client, auth_headers["headers"])

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "fake"
    words = captured[0]["context_words"]
    assert "秀兰" in words and "社区医院" in words
    # 转写文本 "今天秀兰陪我去公园散步" 含 "秀兰"，不含 "社区医院"
    assert body["audio_metrics"]["lexicon_hit_rate"] == 0.5


def test_lexicon_scoped_to_current_user(client, auth_headers):
    """A 请求只能带 A 的词典词，B 的词不得串进 A 的百炼 context。"""
    other = _login(client, "13900111003", "隔壁老王")
    client.post("/api/v1/lexicon/", headers=other,
                json={"word": "别人家的奶奶", "word_type": "person"})
    client.post("/api/v1/lexicon/", headers=auth_headers["headers"],
                json={"word": "秀兰", "word_type": "person"})

    captured = []
    with patch("app.routers.stt._convert_to_wav", return_value=True), \
         patch("app.routers.stt.resolve_chain", return_value=[_fake_provider(captured)]):
        r = _upload(client, auth_headers["headers"])

    assert r.status_code == 200
    words = captured[0]["context_words"]
    assert "秀兰" in words
    assert "别人家的奶奶" not in words


def test_empty_lexicon_passes_empty_list(client, auth_headers):
    """没配词典时传空列表：bailian 侧 build_context_message 对空表
    返回 None、不发空 system message，这是既定契约。"""
    captured = []
    with patch("app.routers.stt._convert_to_wav", return_value=True), \
         patch("app.routers.stt.resolve_chain", return_value=[_fake_provider(captured)]):
        r = _upload(client, auth_headers["headers"])

    assert r.status_code == 200
    assert captured[0]["context_words"] == []


def test_recent_words_first(client, auth_headers):
    """无频次数据时按 created_at 倒序：最近加的词排前面，
    被 2000 字符截断时落掉的是最早加的词。"""
    # 先加"旧词"再加"新词"（自增 created_at）
    client.post("/api/v1/lexicon/", headers=auth_headers["headers"],
                json={"word": "旧邻居", "word_type": "person"})
    client.post("/api/v1/lexicon/", headers=auth_headers["headers"],
                json={"word": "新邻居", "word_type": "person"})

    captured = []
    with patch("app.routers.stt._convert_to_wav", return_value=True), \
         patch("app.routers.stt.resolve_chain", return_value=[_fake_provider(captured)]):
        r = _upload(client, auth_headers["headers"])

    assert r.status_code == 200
    words = captured[0]["context_words"]
    assert words.index("新邻居") < words.index("旧邻居")


def test_all_provider_failure_still_503(client, auth_headers):
    """接线词典不改变降级语义：链上全失败仍 503。"""
    from app.services.asr_providers import TranscriptionResult

    def always_fail(wav_path, context_words, language):
        return TranscriptionResult("", "fake", "fake-model", error="模拟故障")

    with patch("app.routers.stt._convert_to_wav", return_value=True), \
         patch("app.routers.stt.resolve_chain",
               return_value=[SimpleNamespace(name="fake", available=lambda: True,
                                             transcribe=always_fail)]):
        r = _upload(client, auth_headers["headers"])

    assert r.status_code == 503
