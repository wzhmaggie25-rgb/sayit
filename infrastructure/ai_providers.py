"""AI post-processing providers — all speak OpenAI-compatible /v1/chat/completions."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Connection pool (reuse TCP/TLS, avoid handshake per request) ──
_http_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    """Lazy-init a pooled HTTP client with keep-alive."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            trust_env=False,
        )
    return _http_client


@dataclass
class AIProvider:
    """Single AI provider config."""
    id: str
    name: str
    endpoint: str
    api_key: str = ""
    model: str = ""
    enabled: bool = True
    priority: int = 0
    extra_params: dict = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.api_key.strip())


PROVIDER_REGISTRY = {
    "aliyun": {
        "name": "阿里云百炼",
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "default_model": "qwen-flash",           # qwen-flash 是北京地域稳定别名
        "extra": {},
    },
    "volcengine": {
        "name": "火山方舟",
        "endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "default_model": "doubao-seed-2-0-mini-260428",  # 以控制台确切日期版为准
        "extra": {"thinking": {"type": "disabled"}},
    },
    "deepseek": {
        "name": "DeepSeek",
        "endpoint": "https://api.deepseek.com/v1/chat/completions",
        "default_model": "deepseek-v4-flash",    # 注意 chat/reasoner 2026-07-24 停用
        "extra": {"thinking": {"type": "disabled"}},  # 关思考模式节省延迟
    },
    "openai": {
        "name": "OpenAI",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
        "extra": {},
    },
    "claude": {
        "name": "Claude (OpenRouter)",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "anthropic/claude-sonnet-4-6",
        "extra": {},
    },
    "zhipu": {
        "name": "智谱 GLM",
        "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "default_model": "glm-4-flash",
        "extra": {},
    },
    "ollama": {
        "name": "Ollama 本地",
        "endpoint": "http://localhost:11434/v1/chat/completions",
        "default_model": "qwen3",
        "extra": {},
    },
    "openai_compatible": {
        "name": "OpenAI 兼容",
        "endpoint": "",
        "default_model": "",
        "extra": {},
    },
}


def build_providers(config: dict) -> list[AIProvider]:
    """Build prioritized AI provider list from config.json."""
    result = []

    # Check for explicit ai_providers list first
    explicit = config.get("ai_providers", [])
    if explicit:
        for i, p in enumerate(explicit):
            pid = p.get("id", "")
            pk = p.get("api_key", "").strip()
            # Fallback: read key from top-level section if ai_providers entry is empty
            if not pk and pid in config:
                if pid == "volcengine":
                    pk = config[pid].get("ai", {}).get("api_key", "")
                else:
                    pk = config[pid].get("api_key", "")
            if pk and p.get("enabled", True):
                reg = PROVIDER_REGISTRY.get(pid, {})
                extra = reg.get("extra", {})
                ep = p.get("endpoint", "") or reg.get("endpoint", "")
                # ── [AI-KEY] diagnostic — log key source before building provider ──
                logger.info(
                    "[AI-KEY] provider=%s key_source=%s key_preview=%s endpoint=%s model=%s",
                    pid,
                    "explicit" if p.get("api_key", "").strip()
                    else ("asr_access_token_FALLBACK" if pid == "volcengine" else "top_level"),
                    (pk[:6] + "..." + pk[-4:]) if len(pk) > 10 else "[empty]",
                    ep if ep else "[empty]",
                    p.get("model", "") or reg.get("default_model", ""))
                result.append(AIProvider(
                    id=p.get("id", ""),
                    name=p.get("name", p.get("id", "")),
                    endpoint=ep,
                    api_key=pk,
                    model=_force_non_reasoning_model(
                        pid, p.get("model", "") or reg.get("default_model", "")),
                    priority=i,
                    extra_params=extra,
                ))
        if result:
            return result
        # Explicit list produced no usable providers — fall through to legacy sections

    # Fallback: build from legacy config sections
    a = config.get("aliyun", {})
    aliyun_key = a.get("api_key", "").strip()
    if aliyun_key:
        reg = PROVIDER_REGISTRY["aliyun"]
        result.append(AIProvider(
            id="aliyun", name=reg["name"], endpoint=reg["endpoint"],
            api_key=aliyun_key,
            model=_force_non_reasoning_model(
                "aliyun", a.get("correction_model", reg["default_model"])),
            priority=0, extra_params=reg["extra"]))

    v_ai = config.get("volcengine", {}).get("ai", {})
    volc_key = v_ai.get("api_key", "").strip()
    if volc_key:
        reg = PROVIDER_REGISTRY["volcengine"]
        ep = v_ai.get("endpoint", reg["endpoint"])
        if ep and "/chat/completions" not in ep:
            ep = ep.rstrip("/") + "/chat/completions"
        # ── [AI-KEY-legacy] diagnostic — log key source before building provider ──
        logger.info(
            "[AI-KEY-legacy] provider=volcengine key_source=volcengine.ai.api_key "
            "key_preview=%s endpoint=%s model=%s",
            (volc_key[:6] + "..." + volc_key[-4:]) if len(volc_key) > 10 else "[empty]",
            ep,
            v_ai.get("correction_model", reg["default_model"]))
        result.append(AIProvider(
            id="volcengine", name=reg["name"], endpoint=ep,
            api_key=volc_key,
            model=_force_non_reasoning_model(
                "volcengine", v_ai.get("correction_model", reg["default_model"])),
            priority=len(result), extra_params=reg["extra"]))

    # ── DeepSeek (legacy config) ──
    ds = config.get("deepseek", {})
    ds_key = ds.get("api_key", "").strip()
    if ds_key:
        reg = PROVIDER_REGISTRY["deepseek"]
        result.append(AIProvider(
            id="deepseek", name=reg["name"], endpoint=reg["endpoint"],
            api_key=ds_key,
            model=_force_non_reasoning_model(
                "deepseek", ds.get("correction_model", reg["default_model"])),
            priority=len(result), extra_params=reg["extra"]))

    return result


def _force_non_reasoning_model(provider_id: str, model: str) -> str:
    """Keep voice post-processing on fast non-reasoning chat models."""
    model = (model or "").strip()
    lowered = model.lower()
    if provider_id == "deepseek" and (
        "reasoner" in lowered or "r1" in lowered or "thinking" in lowered
    ):
        logger.warning("[AI-NO-REASONING] provider=deepseek model=%r -> deepseek-v4-flash", model)
        return "deepseek-v4-flash"
    if provider_id == "volcengine" and (
        "thinking" in lowered or "reasoning" in lowered or "r1" in lowered
    ):
        logger.warning(
            "[AI-NO-REASONING] provider=volcengine model=%r -> doubao-seed-2-0-mini-260428",
            model)
        return "doubao-seed-2-0-mini-260428"
    if provider_id == "aliyun" and (
        "thinking" in lowered or "reasoning" in lowered or "qwq" in lowered
    ):
        logger.warning("[AI-NO-REASONING] provider=aliyun model=%r -> qwen-flash", model)
        return "qwen-flash"
    return model


def get_active_provider(providers: list[AIProvider]) -> Optional[AIProvider]:
    for p in sorted(providers, key=lambda x: x.priority):
        if p.available:
            return p
    return None


# ── Display name mapping (single source of truth) ──────────
PROVIDER_DISPLAY = {
    "aliyun": "阿里云",
    "volcengine": "火山引擎",
    "deepseek": "DeepSeek",
    "onnx": "本地 ONNX",
    "openai": "OpenAI",
    "claude": "Claude",
    "zhipu": "智谱 GLM",
    "ollama": "Ollama",
}

# ── ASR engine display name mapping ────────────────────────
ASR_DISPLAY = {
    "aliyun": ("阿里云", "DashScope"),
    "volcengine": ("火山引擎", "Volcengine v3"),
    "onnx": ("本地", "SenseVoiceSmall"),
}


def call_provider(provider: AIProvider, system_prompt: str, text: str,
                  timeout: float = 60.0) -> tuple[str, str, str]:
    """Send text through an AI provider for correction.

    Returns (corrected_text, provider_id, model_name).
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": f"请处理以下文本：\n\n{text}"})

    body = {
        "model": provider.model,
        "messages": messages,
        "max_tokens": 4096,              # 闪电说 v0.7.1 EXE 确认
        "temperature": 0.1,              # 闪电说 v0.7.1 EXE 确认
    }
    body.update(provider.extra_params)
    _force_non_reasoning_request(provider, body)

    logger.info("[LLM-REQ] model=%s endpoint=%s len=%d input=%r",
                provider.model, provider.endpoint, len(text), text)

    client = _get_client()
    resp = client.post(
        provider.endpoint,
        headers={"Authorization": f"Bearer {provider.api_key}"},
        json=body,
        timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    result = data["choices"][0]["message"]["content"].strip()
    logger.info("[LLM-RESP] model=%s len=%d output=%r",
                provider.model, len(result), result)
    logger.info("[AI:%s] processed %d→%d chars", provider.id, len(text), len(result))
    return result, provider.id, provider.model


def _force_non_reasoning_request(provider: AIProvider, body: dict):
    """Disable provider-specific reasoning modes when the API supports the flag."""
    body.pop("reasoning", None)
    body.pop("reasoning_effort", None)
    body.pop("include_reasoning", None)
    if provider.id in ("deepseek", "volcengine"):
        body["thinking"] = {"type": "disabled"}
    logger.info(
        "[AI-NO-REASONING] provider=%s model=%s thinking=%r",
        provider.id, provider.model, body.get("thinking", "not_applicable"))


def test_provider(pc: AIProvider, timeout: float = 15.0) -> tuple:
    """Test a provider's connection. Returns (ok: bool, message: str)."""
    try:
        body = {
            "model": pc.model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }
        body.update(pc.extra_params)
        _force_non_reasoning_request(pc, body)
        r = _get_client().post(
            pc.endpoint,
            headers={"Authorization": f"Bearer {pc.api_key}"},
            json=body)
        if r.status_code == 200:
            return True, "连接成功"
        return False, f"HTTP {r.status_code}"
    except httpx.TimeoutException:
        return False, "连接超时"
    except Exception as e:
        logger.warning("test_provider %s failed: %s", pc.id, e)
        return False, "连接失败"
