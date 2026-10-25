"""语音识别路由：provider 链调度，离线优先。

链形态（resolve_chain，各节点 available() 自筛缺席）：
- 主位 asr_provider=bailian → [bailian, volc, vosk]
- 主位 volc → [volc, vosk]；主位 vosk → [vosk]；none → []
火山收编自远端 48ca95a 的内联实现（方言/口音是离线小模型盲区，
在线第二意见），协议层见 services/volc_asr.py。

词典热词：/stt/transcribe 需登录，从当前用户 custom_lexicon 拉热词，
经 provider.transcribe(wav, context_words, lang) 传入链上百炼的 system
context（vosk / volc 忽略该参数）。
"""
import os
import wave
import struct
import tempfile
import logging
import subprocess
from typing import Dict, Any, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import CustomLexicon, User
from app.routers.auth import get_current_user
from app.services.asr_providers import resolve_chain

logger = logging.getLogger("cognitive_garden")
router = APIRouter(prefix="/stt", tags=["Speech-to-Text"])


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
async def transcribe_audio(
    audio: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接收音频文件，返回中文语音识别结果 + 语音认知指标。

    需登录：词典热词按当前用户拉取，喂给链上百炼的 system context
    （vosk / volc 忽略该参数）。链式降级：主 provider 失败静默落下一个，
    都不行才 503。confidence 是启发式（字符密度 + 词典命中率），
    不是 provider 返回的：qwen3-asr-flash 不返回置信度，两者都是编的。
    """
    if not audio.content_type or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="请上传音频文件")

    suffix = ".webm" if "webm" in audio.content_type else ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    wav_path = tmp_path.rsplit(".", 1)[0] + "_16k.wav"
    try:
        if not _convert_to_wav(tmp_path, wav_path):
            # ffmpeg 等部署细节只进日志（_convert_to_wav 已记），给用户的是可行动的人话
            logger.error("音频转换失败，用户侧返回兜底文案")
            raise HTTPException(status_code=500, detail="语音服务暂时开小差了，请稍后再试")

        settings = get_settings()
        chain = resolve_chain(settings.asr_provider, settings)

        # 词典热词：从当前用户的 custom_lexicon 拉取，喂给百炼的 system context
        context_words = _get_lexicon_words(db, current_user.id)

        last_error = "无可用 ASR provider"
        for provider in chain:
            try:
                result = provider.transcribe(wav_path, context_words, "zh")
                if result.ok:
                    audio_metrics = _extract_audio_features(wav_path, result.text)
                    audio_metrics["lexicon_hit_rate"] = _lexicon_hit_rate(
                        result.text, context_words)
                    return {
                        "text": result.text,
                        "confidence": _heuristic_confidence(result.text, audio_metrics),
                        "source": result.provider,
                        "audio_metrics": audio_metrics,
                    }
                last_error = result.error or "空结果"
                logger.info("ASR %s 未产出: %s", provider.name, last_error)
            except Exception as e:
                last_error = str(e)
                logger.error("ASR %s 异常: %s", provider.name, e, exc_info=True)

        # 内部错误明细（last_error）只进日志，不透给终端用户
        logger.error("全部 ASR provider 失败：%s", last_error)
        return JSONResponse(status_code=503, content={
            "detail": "没听清，请再试一次；多次不行请稍后再试"
        })

    finally:
        for p in (tmp_path, wav_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _get_lexicon_words(db: Session, user_id: str, limit: int = 200) -> List[str]:
    """当前用户自定义词典的热词，新加的优先（created_at 倒序）。

    词典表没有命中计数字段，"最近加的" 是 "用户当前在意" 的最好可得代理；
    build_context_message 再按字符数截断，落掉的是最早加的词。
    vosk 不消费该参数（Kaldi 小模型无热词机制），volc 的一句话识别协议
    也没有热词字段；分词侧词典在 nlp.py，走的是会话创建时的另一条传参
    路径，与这里互不影响。
    """
    rows = (
        db.query(CustomLexicon.word)
        .filter(CustomLexicon.user_id == user_id)
        .order_by(CustomLexicon.created_at.desc())
        .limit(limit)
        .all()
    )
    return [w for (w,) in rows if w and w.strip()]


def _lexicon_hit_rate(text: str, lexicon_words: List[str]) -> float:
    """词典词在转写文本中的命中率。词典为空时返回 0.0（不可解释）。"""
    if not lexicon_words or not text:
        return 0.0
    hits = sum(1 for w in lexicon_words if w in text)
    return round(hits / len(lexicon_words), 3)


def _heuristic_confidence(text: str, audio_metrics: dict) -> float:
    """启发式置信度：字符密度。

    老人正常语速约 2–5 字/秒。过快可能是音频有噪声被当语音，
    过慢可能是长停顿或转写失败。这是拍的，不是标定的 ——
    试点期的 low_confidence 分布会告诉我们阈值该定在哪。
    """
    duration = audio_metrics.get("duration_sec", 0)
    chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if duration <= 0:
        return 0.0
    cps = chars / duration
    # 线性映射：1 cps → 0.3，3 cps → 0.8，5 cps → 1.0，超出截断
    conf = max(0.0, min(1.0, 0.3 + (cps - 1.0) * 0.25))
    return round(conf, 3)


@router.get("/health")
async def stt_health():
    """STT 服务健康检查：报告 provider 链上每个节点的可用性"""
    settings = get_settings()
    chain = resolve_chain(settings.asr_provider, settings)
    available = bool(chain)
    return {
        "status": "ok" if available else "unavailable",
        "available": available,
        "provider_setting": settings.asr_provider,
        "chain": [p.name for p in chain],
        "language": "zh-CN",
    }
