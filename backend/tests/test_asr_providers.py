"""ASR provider 链与百炼集成测试（HTTP 全 mock，不发真请求）"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.services.asr_providers import (
    TranscriptionResult,
    build_context_message,
    resolve_chain,
)
from app.services.asr_providers.bailian import BailianProvider
from app.services.asr_providers.volc import VolcProvider


def _settings(provider="vosk", bailian_key="", volc_configured=False, **kw):
    s = MagicMock()
    s.asr_provider = provider
    s.asr_model_path = ""            # vosk available() → False（没模型文件）
    s.bailian_api_key = bailian_key
    s.bailian_asr_model = "qwen3-asr-flash"
    s.bailian_asr_timeout = 5.0
    s.bailian_context_words_max = 2000
    s.bailian_base_url = ""
    s.bailian_region = "cn-beijing"
    s.bailian_workspace_id = "ws-test"
    s.asr_volc_app_id = "app-test" if volc_configured else ""
    s.asr_volc_token = "tok-test" if volc_configured else ""
    s.asr_volc_cluster = "cluster-test" if volc_configured else ""
    s.asr_volc_timeout = 15.0
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------- 链解析

def test_no_key_means_vosk_only():
    s = _settings(provider="bailian", bailian_key="")
    chain = resolve_chain("bailian", s)
    # vosk available() 为 False（无模型文件），百炼无密钥 → 空链
    assert all(p.name != "bailian" for p in chain)


def test_bailian_key_activates_cloud_provider():
    s = _settings(provider="bailian", bailian_key="sk-test")
    # vosk available() 仍为 False（无模型文件），百炼有密钥
    with patch("app.services.asr_providers.vosk.VoskProvider.available", return_value=False):
        chain = resolve_chain("bailian", s)
    assert [p.name for p in chain] == ["bailian"]


def test_unknown_provider_falls_back_to_vosk():
    s = _settings(provider="whisper")
    # 显式钉住 vosk 可用：该测试验证的是"未知 provider 回退到 vosk"的顺序，
    # 不应依赖本地是否恰好有 vosk 模型文件——开发机有模型、CI 没有，
    # 曾导致本地全绿、CI 的 backend-test 红（#61 合并前最后一个拦路石）。
    with patch("app.services.asr_providers.vosk.VoskProvider.available", return_value=True):
        chain = resolve_chain("whisper", s)
    assert [p.name for p in chain] == ["vosk"]


def test_none_provider_gives_empty_chain():
    s = _settings(provider="none")
    chain = resolve_chain("none", s)
    assert all(p.name != "bailian" for p in chain)


# ---------------------------------------------------------------- context

def test_context_empty_returns_none():
    assert build_context_message([]) is None
    assert build_context_message(["", "  "]) is None


def test_context_joins_words_with_chinese_delimiter():
    msg = build_context_message(["秀兰", "建国"])
    assert "秀兰" in msg and "建国" in msg
    assert "、" in msg


def test_context_truncates_at_max():
    words = [f"词{i:04d}" for i in range(2000)]
    msg = build_context_message(words, max_len=500)
    assert len(msg) <= 500


# ---------------------------------------------------------------- 百炼转写

def _mock_response(text="今天秀兰陪我去公园"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": text}}],
    }
    return resp


def test_bailian_available_requires_key():
    assert BailianProvider(_settings(bailian_key="")).available() is False
    assert BailianProvider(_settings(bailian_key="sk-x")).available() is True


def test_bailian_transcribe_success():
    import tempfile, os
    s = _settings(bailian_key="sk-test")
    p = BailianProvider(s)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 100)
        wav = f.name
    try:
        with patch("httpx.Client.post", return_value=_mock_response("今天秀兰陪我去公园")):
            r = p.transcribe(wav, ["秀兰", "公园"], "zh")
        assert r.ok
        assert "秀兰" in r.text
        assert r.provider == "bailian"
    finally:
        os.unlink(wav)


def test_bailian_transcribe_http_error():
    import tempfile, os, httpx
    s = _settings(bailian_key="sk-test")
    p = BailianProvider(s)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 100)
        wav = f.name
    try:
        resp = MagicMock()
        resp.status_code = 429
        resp.text = "rate limited"
        with patch("httpx.Client.post",
                   side_effect=httpx.HTTPStatusError("429", request=MagicMock(), response=resp)):
            r = p.transcribe(wav, [], None)
        assert not r.ok
        assert "429" in r.error
    finally:
        os.unlink(wav)


def test_bailian_itn_disabled_in_request_body():
    """enable_itn 必须显式 false：防止后续模型升级引入润色。"""
    import tempfile, os
    s = _settings(bailian_key="sk-test")
    p = BailianProvider(s)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 100)
        wav = f.name
    captured = {}
    def fake_post(self, url, json=None, headers=None, **kw):
        captured["body"] = json
        return _mock_response("test")
    try:
        with patch("httpx.Client.post", new=fake_post):
            p.transcribe(wav, [], None)
        assert captured["body"]["asr_options"]["enable_itn"] is False
    finally:
        os.unlink(wav)


def test_bailian_context_system_message_included():
    import tempfile, os
    s = _settings(bailian_key="sk-test")
    p = BailianProvider(s)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 100)
        wav = f.name
    captured = {}
    def fake_post(self, url, json=None, headers=None, **kw):
        captured["body"] = json
        return _mock_response("test")
    try:
        with patch("httpx.Client.post", new=fake_post):
            p.transcribe(wav, ["秀兰", "建国"], None)
        msgs = captured["body"]["messages"]
        assert msgs[0]["role"] == "system"
        assert "秀兰" in msgs[0]["content"]
    finally:
        os.unlink(wav)


# ---------------------------------------------------------------- 火山收编
# 远端 48ca95a 的内联 volc→google 降级并入 provider 链。协议层行为由
# test_volc_asr.py（FakeWS 钉帧结构）覆盖；这里只测包装层与链解析。

def test_volc_unconfigured_self_excludes_from_bailian_chain():
    """火山三项配置不齐 → 链上自动缺席，行为等同 [bailian] → vosk。"""
    s = _settings(provider="bailian", bailian_key="sk-test")   # volc 为空
    with patch("app.services.asr_providers.vosk.VoskProvider.available", return_value=False):
        chain = resolve_chain("bailian", s)
    assert [p.name for p in chain] == ["bailian"]


def test_volc_configured_joins_between_bailian_and_vosk():
    """主位百炼 + 火山已配置 → [bailian, volc]（vosk 无模型缺席）。
    火山在线补位语义：方言/口音是离线小模型盲区。"""
    s = _settings(provider="bailian", bailian_key="sk-test", volc_configured=True)
    with patch("app.services.asr_providers.vosk.VoskProvider.available", return_value=False):
        chain = resolve_chain("bailian", s)
    assert [p.name for p in chain] == ["bailian", "volc"]


def test_volc_primary_chain():
    s = _settings(provider="volc", volc_configured=True)
    with patch("app.services.asr_providers.vosk.VoskProvider.available", return_value=False):
        chain = resolve_chain("volc", s)
    assert [p.name for p in chain] == ["volc"]


def test_volc_availability_requires_all_three_settings():
    assert VolcProvider(_settings(volc_configured=False)).available() is False
    partial = _settings()
    partial.asr_volc_app_id = "app"
    partial.asr_volc_token = "tok"          # cluster 仍为空
    assert VolcProvider(partial).available() is False
    assert VolcProvider(_settings(volc_configured=True)).available() is True


def test_volc_transcribe_success_error_and_empty():
    import tempfile, os
    s = _settings(volc_configured=True)
    p = VolcProvider(s)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 100)
        wav = f.name
    try:
        with patch("app.services.volc_asr.transcribe_wav", return_value="今天陪秀兰去公园"):
            r = p.transcribe(wav, ["秀兰"], "zh")
        assert r.ok and r.provider == "volc"
        assert "秀兰" in r.text and r.model == "cluster-test"

        with patch("app.services.volc_asr.transcribe_wav",
                   side_effect=RuntimeError("handshake timeout")):
            r2 = p.transcribe(wav, [], None)
        assert not r2.ok and "handshake timeout" in r2.error

        with patch("app.services.volc_asr.transcribe_wav", return_value=""):
            r3 = p.transcribe(wav, [], None)
        assert not r3.ok and "未识别到内容" in r3.error
    finally:
        os.unlink(wav)


def test_volc_timeout_config_passed_through():
    import tempfile, os
    s = _settings(volc_configured=True, asr_volc_timeout=7.5)
    p = VolcProvider(s)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"\x00" * 100)
        wav = f.name
    captured = {}
    def fake_wav(wav_path, app_id, token, cluster, timeout=15):
        captured["timeout"] = timeout
        captured["args"] = (app_id, token, cluster)
        return "文本"
    try:
        with patch("app.services.volc_asr.transcribe_wav", new=fake_wav):
            p.transcribe(wav, [], None)
        assert captured["timeout"] == 7.5
        assert captured["args"] == ("app-test", "tok-test", "cluster-test")
    finally:
        os.unlink(wav)
