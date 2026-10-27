# ============ 阿里云百炼 DashScope ASR ============
"""qwen3-asr-flash 转写：OpenAI 兼容端点 + base64 Data URL + 词典上下文。

API 格式来源：help.aliyun.com/zh/model-studio/qwen-asr-api-reference（2026-10 查证）。
关键约束：
- 音频 ≤3 分钟、base64 后 ≤10MB（60 秒日课远在限内）
- enable_itn 保持 False：逆文本标准化不删语气词（那是 qwen-audio-3.0 系列的
  "原生润色"，qwen3-asr-flash 没有），但为了防止后续模型升级引入润色，
  这里显式关掉 ITN 并加注释
- context（实体词表）走 system message，必须放第一位
- language 只在已知时指定；混合语种不设
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import List, Optional

from app.services.asr_providers import (
    TranscriptionResult,
    build_context_message,
)

logger = logging.getLogger("cognitive_garden")


class BailianProvider:
    name = "bailian"

    def __init__(self, settings):
        self._settings = settings

    def available(self) -> bool:
        """无副作用检查：密钥与工作空间 ID 是否已配。不发网络请求。"""
        return bool(self._settings.bailian_api_key)

    def transcribe(
        self, wav_path: str, context_words: List[str], language: Optional[str]
    ) -> TranscriptionResult:
        try:
            import httpx
        except ImportError:
            return TranscriptionResult("", self.name, self._settings.bailian_asr_model,
                                       error="httpx 未安装")

        audio_b64 = base64.b64encode(Path(wav_path).read_bytes()).decode()
        mime = "audio/wav"
        data_uri = f"data:{mime};base64,{audio_b64}"

        messages: list = []
        ctx = build_context_message(context_words,
                                    self._settings.bailian_context_words_max)
        if ctx:
            messages.append({"role": "system", "content": ctx})
        messages.append({
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
        })

        asr_options = {"enable_itn": False}
        if language:
            asr_options["language"] = language

        url = self._base_url().rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.bailian_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._settings.bailian_asr_model,
            "messages": messages,
            "stream": False,
            # OpenAI SDK 用 extra_body 传 asr_options；直接 HTTP 就放顶层
            "asr_options": asr_options,
        }

        try:
            with httpx.Client(timeout=self._settings.bailian_asr_timeout) as client:
                resp = client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "") or "").strip()
            if not text:
                return TranscriptionResult("", self.name, self._model(),
                                           error="百炼返回空文本")
            return TranscriptionResult(text, self.name, self._model())
        except httpx.HTTPStatusError as e:
            logger.error("百炼 ASR HTTP %d: %s", e.response.status_code, e.response.text[:300])
            return TranscriptionResult("", self.name, self._model(),
                                       error=f"HTTP {e.response.status_code}")
        except Exception as e:
            logger.error("百炼 ASR 调用失败: %s", e, exc_info=True)
            return TranscriptionResult("", self.name, self._model(), error=str(e))

    def _base_url(self) -> str:
        s = self._settings
        if s.bailian_base_url:
            return s.bailian_base_url
        region = s.bailian_region
        if s.bailian_workspace_id:
            return f"https://{s.bailian_workspace_id}.{region}.maas.aliyuncs.com/compatible-mode/v1"
        # 不带 workspace 的公共端点
        return f"https://{region}.maas.aliyuncs.com/compatible-mode/v1"

    def _model(self) -> str:
        return self._settings.bailian_asr_model
