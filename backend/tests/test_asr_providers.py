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


def _settings(provider="vosk", bailian_key="", **kw):
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
    chain = resolve_chain("whisper", s)
    # vosk available() 为 False（无模型），但链里至少有 vosk 条目
    assert any(p.name == "vosk" for p in chain)


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
