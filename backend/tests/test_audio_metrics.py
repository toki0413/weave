"""语音认知指标测试"""
import struct
import wave
import tempfile
import os

import pytest

from app.routers.stt import _extract_audio_features


def _make_test_wav(duration_sec=1.0, framerate=16000, amplitude=1000):
    """生成一个 16kHz 单声道 16bit 正弦波 WAV 文件，用于测试"""
    n_frames = int(framerate * duration_sec)
    samples = []
    for i in range(n_frames):
        # 400Hz 正弦波
        val = int(amplitude * (i / n_frames) * (1 if i % 2 == 0 else -1))
        samples.append(val)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack(f"{len(samples)}h", *samples))
    return tmp.name


def test_extract_audio_features_basic():
    """从测试 WAV 中提取基础音频指标"""
    path = _make_test_wav(duration_sec=1.0)
    try:
        features = _extract_audio_features(path, "今天在公园散步")
        assert "duration_sec" in features
        assert "speech_ratio" in features
        assert "pause_count" in features
        assert "words_per_minute" in features
        assert features["duration_sec"] > 0
        # 有中文文本且时长 > 0 时，WPM 应大于 0
        assert features["words_per_minute"] > 0
    finally:
        os.unlink(path)


def test_extract_audio_features_empty_text():
    """空文本时 WPM 为 0"""
    path = _make_test_wav(duration_sec=0.5)
    try:
        features = _extract_audio_features(path, "")
        assert features["words_per_minute"] == 0.0
    finally:
        os.unlink(path)


def test_extract_audio_features_invalid_path():
    """无效路径应返回零值指标，不抛异常"""
    features = _extract_audio_features("/nonexistent/path.wav", "测试")
    assert features["duration_sec"] == 0.0
    assert features["words_per_minute"] == 0.0
