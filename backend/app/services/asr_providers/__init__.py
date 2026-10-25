# ============ ASR Provider 抽象 ============
"""可插拔的语音识别 provider 链。

设计约束（改动前先读）：
1. 接口契约冻结。POST /stt/transcribe 的响应
   {text, confidence, source, audio_metrics{...}} 一个字段都不改，只往
   audio_metrics 里加字段、source 加新枚举值。前端与 sessions.metrics 的
   消费方零改动。
2. 离线优先不降级为在线强制。没配百炼密钥时行为与之前完全一致。
3. confidence 不由 provider 自己编：qwen3-asr-flash 不返回置信度分数，
   vosk 的 0.9 也是硬编码。真实值由调用方在 stt.py 里用
   _heuristic_confidence(text, audio_metrics, lexicon_words) 统一算，
   provider 只负责转写文本。

为什么要链而不是 if/else：主 provider 失败（网络不可达、配额、超时）时
应静默落到下一个，而不是报 503 让老人看到错误页。链由 config.asr_provider
决定主位，配置齐备的火山在线补位（方言盲区），vosk 永远是末位兜底。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

logger = logging.getLogger("cognitive_garden")


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    model: str
    language: Optional[str] = None
    raw_duration_sec: Optional[float] = None
    error: Optional[str] = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


@runtime_checkable
class ASRProvider(Protocol):
    name: str

    def available(self) -> bool:
        """无副作用检查：密钥在不在、模型文件在不在。"""
        ...

    def transcribe(
        self, wav_path: str, context_words: List[str], language: Optional[str]
    ) -> TranscriptionResult:
        """wav_path: 16kHz 单声道 16bit WAV（调用方已用 ffmpeg 转好）。
        context_words: 用户自定义词典的词（喂给百炼的 system context，
        vosk 侧忽略）。language: ISO 639-1 代码或 None（自动检测）。"""
        ...


def resolve_chain(provider_setting: str, settings) -> List[ASRProvider]:
    """按配置返回 provider 优先级链。vosk 永远在末位兜底。

    火山收编（原 48ca95a 内联版的语义并入链）：主 provider 失败时，
    已配置的火山在线补位（方言/口音是离线小模型的盲区），最后落 vosk。
    各节点 available() 自筛：没配百炼密钥或火山三项配置不齐的，
    链上自动缺席，行为退化为 vosk-only。
    """
    from app.services.asr_providers.bailian import BailianProvider
    from app.services.asr_providers.volc import VolcProvider
    from app.services.asr_providers.vosk import VoskProvider

    vosk = VoskProvider(settings)
    bailian = BailianProvider(settings)
    volc = VolcProvider(settings)
    chains = {
        "bailian": [bailian, volc, vosk],
        "volc": [volc, vosk],
        "vosk": [vosk],
        "none": [],
    }
    chain = chains.get(provider_setting)
    if chain is None:
        logger.warning("未知 asr_provider=%r，降级为 vosk-only", provider_setting)
        chain = [vosk]
    return [p for p in chain if p.available()]


def build_context_message(context_words: List[str], max_len: int = 2000) -> Optional[str]:
    """把用户词典拼成 DashScope 的 system context 文本。

    超长按使用频次截断（调用方保证已按频次排好序）。空词典返回 None，
    不发空 system message（qwen3-asr-flash 对空 context 的行为未定义）。
    """
    words = [w.strip() for w in context_words if w.strip()]
    if not words:
        return None
    text = "这是一位老年人的日常口语叙述。以下是人名、地名和常用词，请准确识别：\n" + "、".join(words)
    return text[:max_len]
