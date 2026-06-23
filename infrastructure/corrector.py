"""AI text correction and organization pipeline."""
from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING

from infrastructure.ai_providers import (
    AIProvider,
    PROVIDER_DISPLAY,
    build_providers,
    call_provider,
    get_active_provider,
)
from infrastructure.config_store import ConfigStore

if TYPE_CHECKING:
    from infrastructure.hotwords_manager import HotwordsManager

logger = logging.getLogger(__name__)

_PROMPT_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def _load_prompt(filename: str) -> str:
    path = os.path.join(_PROMPT_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        logger.warning("Cannot load prompt file: %s", path)
        return ""


_shared = _load_prompt("shared_prefix.txt")
_levels = {
    "none": _load_prompt("level_none.txt"),
    "light": _load_prompt("level_light.txt"),
    "deep": _load_prompt("level_deep.txt"),
}


def build_system_prompt(config: dict) -> str:
    """Build the system prompt for the configured organize_level."""
    level = config.get("organize_level", "light")
    level_prompt = _levels.get(level, _levels["light"])
    parts = [_shared, level_prompt]
    return "\n\n".join(part for part in parts if part)


_CN_PUNCT = {
    ".": "。",
    ",": "，",
    "!": "！",
    "?": "？",
    ";": "；",
    ":": "：",
    "(": "（",
    ")": "）",
}

_FILLER_PREFIX = re.compile(
    r"^(嗯+|呃+|啊+|这个|那个|就是说|就是|然后呢|然后的话|OK|ok)[，,。.!！?\s]*"
)
_FILLER_INLINE = re.compile(
    r"(然后呢|然后的话|就是说|就是这个|就是那个|你知道吧|对吧|是吧|好吧)"
)


def normalize_text(
    text: str,
    enable_disfluency: bool = True,
    enable_punctuation: bool = True,
) -> str:
    """Run deterministic normalization before AI correction."""
    if not text:
        return text
    result = text.strip()

    if enable_punctuation:
        for en, cn in _CN_PUNCT.items():
            result = re.sub(
                rf"([\u4e00-\u9fff]){re.escape(en)}([\u4e00-\u9fff])",
                rf"\1{cn}\2",
                result,
            )

    result = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", result)
    result = re.sub(r"\n{3,}", "\n\n", result)

    if enable_disfluency:
        try:
            level = ConfigStore().get("organize_level", "light")
            if level != "none":
                result = _FILLER_PREFIX.sub("", result)
                result = _FILLER_INLINE.sub("", result)
                result = re.sub(r"([\u4e00-\u9fff]{2,})\1", r"\1", result)
        except Exception:
            pass

    return result.strip()


def _build_hotword_guard(hotwords_list: list[str]) -> str:
    """Layer 3 bodyguard that prevents AI from rewriting hotwords."""
    clean = []
    for word in hotwords_list:
        word = (word or "").strip()
        if word and word not in clean:
            clean.append(word)
    if not clean:
        return ""
    items = ", ".join(f'"{word}"' for word in clean[:50])
    return (
        "\n\n# 热词保护规则\n"
        "以下词是用户词典中的标准写法。必须原样保留它们的拼写、大小写和符号；"
        "如果输入中出现这些词的明显同音、大小写或分词错误，应改回标准写法：\n"
        f"{items}"
    )


def correct_text(
    text: str,
    providers: list[AIProvider] | None = None,
    enable_correction: bool = True,
    enable_structuring: bool = True,
    correction_prompt: str = "",
    structuring_prompt: str = "",
    hotwords_mgr: "HotwordsManager | None" = None,
    enable_disfluency_filter: bool = True,
    enable_auto_structuring: bool = True,
    enable_punctuation: bool = True,
) -> tuple[str, str | None, str | None]:
    """Run text through deterministic normalization and optional AI correction."""
    text = normalize_text(
        text,
        enable_disfluency=enable_disfluency_filter,
        enable_punctuation=enable_punctuation,
    )

    if not enable_correction and not enable_structuring:
        return text, None, None

    if providers is None:
        config = ConfigStore()
        providers = build_providers(config.get_all())

    provider = get_active_provider(providers)
    if provider is None:
        logger.warning("No AI provider available for correction")
        return text, None, None

    config = ConfigStore()
    cfg = config.get_all()
    system_prompt = build_system_prompt(cfg)

    custom = cfg.get("system_prompt", "").strip()
    if custom:
        system_prompt = custom

    user_prefs = cfg.get("structuring_prompt", "").strip()
    if enable_correction and user_prefs:
        system_prompt += "\n\n# 用户自定义要求\n" + user_prefs

    if correction_prompt:
        system_prompt += "\n\n# 纠错补充要求\n" + correction_prompt.strip()
    if structuring_prompt:
        system_prompt += "\n\n# 整理补充要求\n" + structuring_prompt.strip()

    if not enable_auto_structuring:
        system_prompt += "\n\n保持原文结构，不要主动分点、编号或重组段落。"

    if hotwords_mgr is not None:
        guard = _build_hotword_guard(hotwords_mgr.get_words())
        if guard:
            system_prompt += guard
            logger.info("[AI-HOTWORD-GUARD] appending %d hotwords", len(hotwords_mgr.get_words()))

    try:
        return call_provider(provider, system_prompt, text)
    except Exception as e:
        logger.warning("[AI] correction failed: %s", e)
        return text, None, None


class Corrector:
    """Config-driven AI corrector."""

    def __init__(self):
        self.reload_config()

    def reload_config(self):
        config = ConfigStore()
        self._providers = build_providers(config.get_all())
        self._enable_correction = config.get("enable_correction", True)
        self._enable_structuring = config.get("enable_structuring", True)
        self._correction_prompt = config.get("correction_prompt", "")
        self._structuring_prompt = config.get("structuring_prompt", "")
        self._enable_disfluency_filter = config.get("enable_disfluency_filter", True)
        self._enable_auto_structuring = config.get("enable_auto_structuring", True)
        self._enable_punctuation = config.get("enable_punctuation", True)

    def process(self, text: str, hotwords_mgr: "HotwordsManager | None" = None):
        """Return (corrected_text, provider_id, model_name)."""
        return correct_text(
            text,
            self._providers,
            enable_correction=self._enable_correction,
            enable_structuring=self._enable_structuring,
            correction_prompt=self._correction_prompt,
            structuring_prompt=self._structuring_prompt,
            hotwords_mgr=hotwords_mgr,
            enable_disfluency_filter=self._enable_disfluency_filter,
            enable_auto_structuring=self._enable_auto_structuring,
            enable_punctuation=self._enable_punctuation,
        )


def get_active_correction_info() -> dict:
    config = ConfigStore()
    providers = build_providers(config.get_all())
    active = get_active_provider(providers)
    if active:
        return {
            "provider_id": active.id,
            "model_name": active.model,
            "display_name": PROVIDER_DISPLAY.get(active.id, active.id),
            "available": True,
        }
    any_enabled = any(provider.enabled for provider in providers)
    return {
        "provider_id": None,
        "model_name": None,
        "display_name": None,
        "available": False,
        "reason": "disabled" if any_enabled else "not_configured",
    }
