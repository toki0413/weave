"""语音识别路由：Vosk 离线优先，Google 在线降级"""
import os
import json
import wave
import struct
import tempfile
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger("cognitive_garden")
router = APIRouter(prefix="/stt", tags=["Speech-to-Text"])

# Vosk 懒加载：仅在首次调用时初始化，避免无模型时启动失败
_vosk_model = None
_vosk_available = None


def _check_vosk():
    """检查 vosk 是否可用（包 + 模型）"""
    global _vosk_available, _vosk_model
    if _vosk_available is not None:
        return _vosk_available

    settings = get_settings()
    if settings.asr_provider != "vosk":
        _vosk_available = False
        return False

    try:
        from vosk import Model
    except ImportError:
        logger.warning("vosk 包未安装，STT 降级到 Google 在线识别")
        _vosk_available = False
        return False

    model_path = settings.asr_model_path
    if not model_path:
        # 默认查找常见路径
        candidates = [
            Path.home() / ".cognitive-garden" / "vosk-model-small-cn-0.22",
            Path("models") / "vosk-model-small-cn-0.22",
            Path("/usr/share/vosk/vosk-model-small-cn-0.22"),
        ]
        for c in candidates:
            if c.exists():
                model_path = str(c)
                break

    if not model_path or not Path(model_path).exists():
        logger.warning("Vosk 模型未找到，STT 降级到 Google 在线识别。请下载 vosk-model-small-cn-0.22 并配置 asr_model_path")
        _vosk_available = False
        return False

    try:
        _vosk_model = Model(model_path)
        _vosk_available = True
        logger.info("Vosk 模型加载成功: %s", model_path)
        return True
    except Exception as e:
        logger.error("Vosk 模型加载失败: %s", e)
        _vosk_available = False
        return False


def _convert_to_wav(input_path: str, output_path: str) -> bool:
    """用 ffmpeg 将音频转为 16kHz 单声道 WAV（Vosk 要求）"""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", "-f", "wav", output_path],
            capture_output=True, timeout=30, check=True,
        )
        return True
    except FileNotFoundError:
        logger.warning("ffmpeg 未安装，无法转换音频格式")
        return False
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg 转换失败: %s", e.stderr.decode(errors="replace")[:200])
        return False
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg 转换超时")
        return False


def _transcribe_vosk(wav_path: str) -> str:
    """用 Vosk 识别 WAV 文件"""
    from vosk import KaldiRecognizer

    wf = wave.open(wav_path, "rb")
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
        raise ValueError("WAV 格式不符合要求（需 16kHz 单声道 16bit）")

    rec = KaldiRecognizer(_vosk_model, wf.getframerate())
    rec.SetWords(True)

    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            r = json.loads(rec.Result())
            if r.get("text"):
                results.append(r["text"])

    # 最终结果
    final = json.loads(rec.FinalResult())
    if final.get("text"):
        results.append(final["text"])

    wf.close()
    return "".join(results)


def _transcribe_google(audio_path: str) -> str:
    """Google 在线识别降级方案"""
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_path) as source:
        audio_data = recognizer.record(source)
    return recognizer.recognize_google(audio_data, language="zh-CN")


def _extract_audio_features(wav_path: str, text: str) -> Dict[str, Any]:
    """从 16kHz 单声道 WAV 中提取语音认知指标

    指标：
    - duration_sec: 音频总时长（秒）
    - speech_ratio: 语音帧占比（0-1）
    - pause_count: 停顿次数（语音→静音转换次数）
    - words_per_minute: 中文字数/分钟
    """
    try:
        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            duration_sec = n_frames / framerate if framerate else 0

            if sample_width != 2 or n_frames == 0:
                return {
                    "duration_sec": round(duration_sec, 2),
                    "speech_ratio": 0.0,
                    "pause_count": 0,
                    "words_per_minute": 0.0,
                }

            fmt = f"{n_frames * n_channels}h"
            raw = struct.unpack(fmt, wf.readframes(n_frames))
            if n_channels == 2:
                samples = [(raw[i] + raw[i + 1]) / 2 for i in range(0, len(raw), 2)]
            else:
                samples = list(raw)
    except Exception as e:
        logger.warning("音频特征提取失败: %s", e)
        return {
            "duration_sec": 0.0,
            "speech_ratio": 0.0,
            "pause_count": 0,
            "words_per_minute": 0.0,
        }

    if not samples or duration_sec <= 0:
        return {
            "duration_sec": round(duration_sec, 2),
            "speech_ratio": 0.0,
            "pause_count": 0,
            "words_per_minute": 0.0,
        }

    # 20ms 一帧计算能量
    frame_size = max(1, int(framerate * 0.02))
    energies = []
    for i in range(0, len(samples), frame_size):
        frame = samples[i:i + frame_size]
        if frame:
            energy = sum(s * s for s in frame) / len(frame)
            energies.append(energy)

    if not energies:
        return {
            "duration_sec": round(duration_sec, 2),
            "speech_ratio": 0.0,
            "pause_count": 0,
            "words_per_minute": 0.0,
        }

    sorted_energies = sorted(energies)
    threshold = sorted_energies[len(sorted_energies) // 2] * 2.0
    if threshold <= 0:
        threshold = max(energies) * 0.1

    is_speech = [e > threshold for e in energies]
    speech_frames = sum(is_speech)
    speech_ratio = speech_frames / len(is_speech) if is_speech else 0.0

    pause_count = 0
    prev_speech = False
    for s in is_speech:
        if prev_speech and not s:
            pause_count += 1
        prev_speech = s

    # 中文字数/分钟作为语速指标
    chinese_chars = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
    duration_min = duration_sec / 60.0
    wpm = chinese_chars / duration_min if duration_min > 0 else 0.0

    return {
        "duration_sec": round(duration_sec, 2),
        "speech_ratio": round(speech_ratio, 2),
        "pause_count": pause_count,
        "words_per_minute": round(wpm, 1),
    }


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """接收音频文件，返回中文语音识别结果 + 语音认知指标。Vosk 离线优先，Google 在线降级。"""
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="请上传音频文件")

    suffix = ".webm" if "webm" in audio.content_type else ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    wav_path = tmp_path.rsplit(".", 1)[0] + "_16k.wav"
    try:
        # 转换为 16kHz 单声道 WAV
        if not _convert_to_wav(tmp_path, wav_path):
            raise HTTPException(status_code=500, detail="音频格式转换失败，请确保已安装 ffmpeg")

        # Vosk 离线识别
        if _check_vosk():
            try:
                text = _transcribe_vosk(wav_path)
                if text.strip():
                    return {
                        "text": text,
                        "confidence": 0.9,
                        "source": "vosk",
                        "audio_metrics": _extract_audio_features(wav_path, text),
                    }
                return JSONResponse(status_code=422, content={"detail": "无法识别语音，请尝试更清晰的发音"})
            except Exception as e:
                logger.error("Vosk 识别失败，降级到 Google: %s", e)

        # Google 在线降级
        try:
            text = _transcribe_google(wav_path)
            return {
                "text": text,
                "confidence": 1.0,
                "source": "google",
                "audio_metrics": _extract_audio_features(wav_path, text),
            }
        except Exception as e:
            logger.error("Google 识别失败: %s", e)
            if "UnknownValueError" in type(e).__name__:
                return JSONResponse(status_code=422, content={"detail": "无法识别语音，请尝试更清晰的发音"})
            return JSONResponse(status_code=503, content={"detail": "语音识别服务不可用"})

    finally:
        for p in (tmp_path, wav_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _check_google() -> bool:
    """检查 Google 在线识别依赖是否可用"""
    try:
        import speech_recognition as sr  # noqa: F401
        return True
    except ImportError:
        return False


@router.get("/health")
async def stt_health():
    """STT 服务健康检查"""
    vosk_ok = _check_vosk()
    google_ok = _check_google()
    available = vosk_ok or google_ok
    return {
        "status": "ok" if available else "unavailable",
        "available": available,
        "engine": "vosk" if vosk_ok else ("google" if google_ok else "none"),
        "offline": vosk_ok,
        "language": "zh-CN",
    }
