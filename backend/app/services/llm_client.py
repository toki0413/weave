# ============ LLM 客户端：统一 OpenAI 兼容接口 ============
import os
import logging
from typing import Optional, Dict, Any

from app.config import get_settings, Settings

logger = logging.getLogger("cognitive_garden")

# 各 provider 默认 base_url
_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",  # 需走兼容端点
    "deepseek": "https://api.deepseek.com/v1",
}


def _get_base_url(settings: Settings) -> str:
    """确定 LLM API 的 base_url"""
    if settings.llm_base_url:
        return settings.llm_base_url
    return _DEFAULT_BASE_URLS.get(settings.llm_provider, "")


def is_llm_available() -> bool:
    """检查 LLM 配置是否完整可用"""
    settings = get_settings()
    if not settings.llm_provider or not settings.llm_provider.strip():
        return False
    if not settings.llm_api_key or not settings.llm_api_key.strip():
        return False
    if not settings.llm_model or not settings.llm_model.strip():
        return False
    return True


def llm_call(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> str:
    """
    统一调用 LLM，使用 openai 库的兼容模式。
    超时 30 秒，失败时抛出异常。
    返回 LLM 生成的文本内容（已 strip）。
    """
    settings = get_settings()
    if not is_llm_available():
        raise RuntimeError("LLM 未配置")

    api_key = settings.llm_api_key
    _model = model or settings.llm_model
    base_url = _get_base_url(settings)

    if not base_url:
        raise RuntimeError(f"未知的 LLM provider: {settings.llm_provider}")

    try:
        import openai
    except ImportError:
        logger.warning("openai 库未安装，尝试用 httpx 直接请求")
        return _llm_call_via_httpx(
            base_url, api_key, _model, prompt, temperature, max_tokens, system_prompt
        )

    # 使用 openai 兼容模式
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0,
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        raise


def _llm_call_via_httpx(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    system_prompt: Optional[str],
) -> str:
    """openai 库不可用时，用 httpx 直接发 OpenAI 兼容请求（降级）"""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("openai 和 httpx 均未安装，无法调用 LLM")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"] or ""
        return content.strip()


# 便捷包装：让 LLM 返回 JSON 并自动解析
import json as _json


def llm_call_json(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 LLM 并尝试解析返回的 JSON。失败时抛出异常。"""
    raw = llm_call(prompt, model, temperature, max_tokens, system_prompt)
    # 处理 markdown 代码块
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.strip("`").strip()
        if clean.startswith("json"):
            clean = clean[4:].strip()
    try:
        return _json.loads(clean)
    except Exception as e:
        logger.error("LLM 返回内容 JSON 解析失败: %s\n原始内容: %s", e, raw[:500])
        raise RuntimeError(f"LLM 返回内容不是有效 JSON: {e}")
