# ============ Vosk 离线 ASR ============
"""从 routers/stt.py:24-117 搬入，逻辑不改。缺模型时 available() 为 False。"""
from __future__ import annotations

import json
import logging
import wave
from pathlib import Path
from typing import List, Optional

from app.services.asr_providers import TranscriptionResult

logger = logging.getLogger("cognitive_garden")

_vosk_model = None
_vosk_checked = False


class VoskProvider:
    name = "vosk"

    def __init__(self, settings):
        self._settings = settings

    def available(self) -> bool:
        global _vosk_model, _vosk_checked
        if _vosk_checked:
            return _vosk_model is not None
        _vosk_checked = True
        try:
            from vosk import Model
        except ImportError:
            return False
        model_path = self._settings.asr_model_path
        if not model_path:
            for c in [
                Path.home() / ".cognitive-garden" / "vosk-model-small-cn-0.22",
                Path("models") / "vosk-model-small-cn-0.22",
                Path("/usr/share/vosk/vosk-model-small-cn-0.22"),
            ]:
                if c.exists():
                    model_path = str(c)
                    break
        if not model_path or not Path(model_path).exists():
            logger.warning("Vosk 模型未找到，离线 ASR 不可用")
            return False
        _vosk_model = Model(model_path)
        return True

    def transcribe(
        self, wav_path: str, context_words: List[str], language: Optional[str]
    ) -> TranscriptionResult:
        from vosk import KaldiRecognizer

        wf = wave.open(wav_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            wf.close()
            return TranscriptionResult("", self.name, "vosk-small-cn",
                                       error="WAV 格式需 16kHz 单声道 16bit")
        rec = KaldiRecognizer(_vosk_model, wf.getframerate())
        rec.SetWords(True)
        results = []
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                r = json.loads(rec.Result())
                if r.get("text"):
                    results.append(r["text"])
        final = json.loads(rec.FinalResult())
        if final.get("text"):
            results.append(final["text"])
        wf.close()
        text = "".join(results).strip()
        if not text:
            return TranscriptionResult("", self.name, "vosk-small-cn",
                                       error="vosk 未识别到内容")
        return TranscriptionResult(text, self.name, "vosk-small-cn")
