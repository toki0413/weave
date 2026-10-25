# ============ 火山引擎一句话 ASR provider ============
"""把 services/volc_asr.py 包装成 provider 链一环。

来源：origin/master 48ca95a 曾把它以内联方式接在 stt.py 的
vosk→volc→google 顺序里；provider 链重构后改由 resolve_chain 调度，
协议实现（WebSocket 帧、鉴权、gzip 分包）一行不动，仍由
tests/test_volc_asr.py 的协议测试钉住。

设计动机沿用原注释：官方适老场景是方言 + 共情，方言/口音正是
离线小模型的盲区 —— vosk 空结果或百炼失败时，火山在链上是
"在线第二意见"。

热词：一句话识别协议的 full client request 不带热词字段，
context_words 被忽略（与 vosk 同）。接入热词需要改协议帧并拿
真实密钥验证，目前只做了百炼侧。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.services.asr_providers import TranscriptionResult

logger = logging.getLogger("cognitive_garden")


class VolcProvider:
    name = "volc"

    def __init__(self, settings):
        self._settings = settings

    def available(self) -> bool:
        """无副作用检查：三项配置齐备才启用（与原内联版语义一致）。"""
        s = self._settings
        return bool(s.asr_volc_app_id and s.asr_volc_token and s.asr_volc_cluster)

    def transcribe(
        self, wav_path: str, context_words: List[str], language: Optional[str]
    ) -> TranscriptionResult:
        try:
            from app.services.volc_asr import transcribe_wav
        except Exception as e:   # websocket-client 未安装等导入失败
            return TranscriptionResult("", self.name, self._model(),
                                       error=f"火山依赖不可用: {e}")

        try:
            text = transcribe_wav(
                wav_path,
                self._settings.asr_volc_app_id,
                self._settings.asr_volc_token,
                self._settings.asr_volc_cluster,
                timeout=self._settings.asr_volc_timeout,
            )
        except Exception as e:
            logger.error("火山 ASR 调用失败: %s", e, exc_info=True)
            return TranscriptionResult("", self.name, self._model(), error=str(e))

        if not text:
            return TranscriptionResult("", self.name, self._model(),
                                       error="火山未识别到内容")
        return TranscriptionResult(text, self.name, self._model())

    def _model(self) -> str:
        """cluster 是火山侧真正区分引擎/音区的标识，充当 model 语义。"""
        return self._settings.asr_volc_cluster or "one-sentence"
