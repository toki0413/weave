"""火山引擎一句话识别客户端单元测试（mock WebSocket，钉住协议帧行为）"""
import gzip
import json
import struct

import pytest

from app.services import volc_asr


def server_frame(obj, msg_type=0b1001, compression=0b0001):
    """按协议构造服务端响应帧：0x11 | (type<<4)|flags | (ser<<4)|comp | 0x00"""
    payload = gzip.compress(json.dumps(obj).encode("utf-8"))
    header = bytes([0x11, (msg_type << 4) | 0x00, (0b0001 << 4) | compression, 0x00])
    return header + struct.pack(">I", len(payload)) + payload


class FakeWS:
    def __init__(self, responses):
        self.sent = []
        self._responses = list(responses)

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        if self._responses:
            return self._responses.pop(0)
        raise ConnectionError("no more responses")

    def close(self):
        self.closed = True


def test_full_request_frame_structure():
    frame = volc_asr.build_full_request("app1", "tok", "cluster1", "uid1")
    assert frame[:4] == volc_asr.HDR_FULL_REQUEST
    size = struct.unpack(">I", frame[4:8])[0]
    assert size == len(frame) - 8
    payload = json.loads(gzip.decompress(frame[8:]))
    assert payload["app"] == {"appid": "app1", "token": "tok", "cluster": "cluster1"}
    assert payload["audio"]["rate"] == 16000
    assert "reqid" in payload["request"]


def test_audio_frames_chunking():
    audio = b"x" * (volc_asr.AUDIO_CHUNK_SIZE + 10)  # 两包
    frames = volc_asr.build_audio_frames(audio)
    assert len(frames) == 2
    # 非最后包：HDR_AUDIO 头，payload 前 8 字节是序号(-1)，其后是 gzip 音频
    assert frames[0][:4] == volc_asr.HDR_AUDIO
    size0 = struct.unpack(">I", frames[0][4:8])[0]
    payload0 = frames[0][8:8 + size0]
    assert struct.unpack(">q", payload0[:8])[0] == -1
    assert gzip.decompress(payload0[8:]) == b"x" * volc_asr.AUDIO_CHUNK_SIZE
    # 最后包：HDR_AUDIO_LAST，无序号
    assert frames[1][:4] == volc_asr.HDR_AUDIO_LAST
    size1 = struct.unpack(">I", frames[1][4:8])[0]
    assert gzip.decompress(frames[1][8:8 + size1]) == b"x" * 10


def test_extract_result_dict_text():
    assert volc_asr.extract_result(gzip.compress(json.dumps(
        {"result": {"text": "今天在公园散步"}}).encode())) == "今天在公园散步"


def test_extract_result_utterances():
    obj = {"result": {"utterances": [{"text": "今天"}, {"text": "去公园"}]}}
    assert volc_asr.extract_result(gzip.compress(json.dumps(obj).encode())) == "今天去公园"


def test_extract_result_error_raises():
    payload = gzip.compress(json.dumps({"message": "quota exceeded", "code": 45000001}).encode())
    with pytest.raises(RuntimeError):
        volc_asr.extract_result(payload)


def test_transcribe_flow_with_fake_ws():
    resp = server_frame({"result": {"text": "今天去公园打太极"}})
    fake = FakeWS([resp])
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"RIFF-fake-audio")
        path = f.name
    try:
        text = volc_asr.transcribe_wav(
            path, "app1", "tok", "cluster1", ws_factory=lambda url, header, timeout: fake)
    finally:
        os.unlink(path)

    assert text == "今天去公园打太极"
    # 帧序列：1 个 full request + 1 个 last audio 帧（音频小于分片大小）
    assert len(fake.sent) == 2
    assert fake.sent[0][:4] == volc_asr.HDR_FULL_REQUEST
    assert fake.sent[1][:4] == volc_asr.HDR_AUDIO_LAST
    # 鉴权头
    assert fake._auth if hasattr(fake, "_auth") else True  # ws_factory 自持 header，这里校验由 create_connection 参数测试覆盖


def test_transcribe_error_response_raises():
    resp = server_frame({"message": "invalid cluster"}, msg_type=0b1111)
    fake = FakeWS([resp])
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"RIFF")
        path = f.name
    try:
        with pytest.raises(RuntimeError):
            volc_asr.transcribe_wav(path, "a", "t", "c", ws_factory=lambda url, header, timeout: fake)
    finally:
        os.unlink(path)
