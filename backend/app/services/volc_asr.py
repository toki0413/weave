"""火山引擎一句话识别客户端（wss://openspeech.bytedance.com/api/v2/asr）

协议要点（官方文档 DoubaoVoice/One-sentencerecognition + 鉴权方法）：
- WebSocket 建连时带 Authorization: Bearer; {token}
- 二进制帧：4 字节头 [版本4b=0001][头大小4b=0001][消息类型4b][flags4b][序列化4b][压缩4b][保留8b]
  + 4 字节大端 payload 长度 + payload
- full client request：类型 0b0001，JSON 序列化 + gzip 压缩
- audio only：类型 0b0010，无序列化 + gzip 压缩；flags 0b0001 表示 payload 前有 8 字节
  大端有符号序号（约定 -1 表示忽略），0b0010 表示最后一个包
- 服务端 full response 类型 0b1001，error 类型 0b1111
- 限一句话场景（≤60s 音频），与织忆 60 秒日课/短叙事完全匹配

依赖 websocket-client（requirements.txt）；未安装或未配置密钥时由调用方回退，
绝不阻塞主识别链路。
"""
import gzip
import json
import logging
import struct
import uuid

logger = logging.getLogger("cognitive_garden")

ASR_WS_URL = "wss://openspeech.bytedance.com/api/v2/asr"

# 帧常量（公开给测试钉住协议行为）
HDR_FULL_REQUEST = b"\x11\x10\x11\x00"   # full client request: JSON + gzip
HDR_AUDIO = b"\x11\x20\x01\x00"          # audio only: 无序列化 + gzip（非最后包，带序号）
HDR_AUDIO_LAST = b"\x11\x22\x01\x00"     # audio only: 最后包，无序号
MSG_TYPE_FULL_SERVER = 0b1001
MSG_TYPE_ERROR = 0b1111
AUDIO_CHUNK_SIZE = 64 * 1024


def _pack(header: bytes, payload: bytes) -> bytes:
    """4 字节头 + 4 字节大端长度 + payload"""
    return header + struct.pack(">I", len(payload)) + payload


def build_full_request(app_id: str, token: str, cluster: str, uid: str,
                       audio_format: str = "wav", rate: int = 16000) -> bytes:
    """构造 full client request 帧（gzip JSON payload）"""
    req = {
        "app": {"appid": app_id, "token": token, "cluster": cluster},
        "user": {"uid": uid},
        "audio": {"format": audio_format, "rate": rate, "bits": 16, "channel": 1},
        "request": {"reqid": str(uuid.uuid4()), "nbest": 1, "show_utterances": False},
    }
    return _pack(HDR_FULL_REQUEST, gzip.compress(json.dumps(req).encode("utf-8")))


def build_audio_frames(audio: bytes) -> list:
    """音频分包：非最后包带 8 字节序号(-1)，最后包无序号"""
    frames = []
    if not audio:
        frames.append(_pack(HDR_AUDIO_LAST, gzip.compress(b"")))
        return frames
    offset = 0
    while offset < len(audio):
        chunk = audio[offset:offset + AUDIO_CHUNK_SIZE]
        offset += len(chunk)
        if offset < len(audio):
            payload = struct.pack(">q", -1) + gzip.compress(chunk)
            frames.append(_pack(HDR_AUDIO, payload))
        else:
            frames.append(_pack(HDR_AUDIO_LAST, gzip.compress(chunk)))
    return frames


def _parse_text(obj) -> str:
    """防御性提取识别文本：不同集群返回结构略有差异"""
    if not isinstance(obj, dict):
        return ""
    result = obj.get("result")
    if isinstance(result, dict):
        text = result.get("text")
        if isinstance(text, str):
            return text
        utterances = result.get("utterances")
        if isinstance(utterances, list) and utterances:
            parts = [u.get("text", "") for u in utterances if isinstance(u, dict)]
            return "".join(parts)
        return ""
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            return first.get("text", "") or ""
    return obj.get("text", "") or ""


def _recv_message(ws):
    """收一帧：返回 (msg_type, payload_bytes)。忽略心跳/ack 类消息。"""
    while True:
        data = ws.recv()
        if isinstance(data, str):
            # 少数集群以文本心跳回包，跳过
            logger.debug("volc asr text frame: %s", data[:100])
            continue
        if len(data) < 8:
            raise ValueError("volc asr: 响应帧头不完整")
        msg_type = (data[1] >> 4) & 0x0F
        compression = data[2] & 0x0F
        size = struct.unpack(">I", data[4:8])[0]
        payload = data[8:8 + size]
        if compression == 0b0001 and payload:
            payload = gzip.decompress(payload)
        if msg_type in (MSG_TYPE_FULL_SERVER, MSG_TYPE_ERROR):
            return msg_type, payload
        # 其他类型（如 audio ack）继续收


def extract_result(payload: bytes) -> str:
    """从 full server response payload 提取文本；error payload 抛异常。

    防御式兼容：接受已解压的 JSON bytes，也接受漏解压的 gzip bytes。
    """
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    obj = json.loads(payload.decode("utf-8"))
    if "message" in obj and "result" not in obj and obj.get("code", 0) not in (0, 1000, 2000):
        raise RuntimeError(f"volc asr error: {obj.get('message')}")
    return _parse_text(obj)


def transcribe_wav(wav_path: str, app_id: str, token: str, cluster: str,
                   ws_factory=None, timeout: int = 15) -> str:
    """同步识别一个 16kHz wav 文件，返回文本。

    ws_factory: 测试注入点，签名 (url, header, timeout) -> ws 对象，
    需提供 send(bytes) 与 recv()。
    """
    import websocket  # 延迟导入：未安装时由调用方回退到下一引擎

    if ws_factory is None:
        def ws_factory(url, header, timeout):
            return websocket.create_connection(url, header=header, timeout=timeout)

    with open(wav_path, "rb") as f:
        audio = f.read()

    uid = str(uuid.uuid4())
    ws = ws_factory(
        ASR_WS_URL,
        [f"Authorization: Bearer; {token}", "Content-Type: application/json"],
        timeout,
    )
    try:
        ws.send(build_full_request(app_id, token, cluster, uid,
                                   audio_format="wav"))
        for frame in build_audio_frames(audio):
            ws.send(frame)

        texts = []
        while True:
            msg_type, payload = _recv_message(ws)
            if msg_type == MSG_TYPE_ERROR:
                raise RuntimeError(f"volc asr error: {payload.decode('utf-8', 'replace')[:200]}")
            text = extract_result(payload)
            if text:
                texts.append(text)
            # full server response 且是最终结果时服务端会关连接或发完即止；
            # 一句话识别为整句返回，收到一次含文本的结果即可结束
            if text:
                break
        return "".join(texts).strip()
    finally:
        try:
            ws.close()
        except Exception:
            pass
