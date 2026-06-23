"""Hotwords three-layer injection logic: ASR context, local correction, LLM prompt."""
from __future__ import annotations

import re


HOTWORD_ALIASES: dict[str, tuple[str, ...]] = {
    "Sayit": ("赛义德", "赛意德", "赛一德", "赛伊特"),
    "Typeless": (
        "泰普勒斯", "太普勒斯", "type less", "Type less",
        "Tablets", "typExcel", "typExcels", "TypeSS", "TypeSS Tablets",
    ),
    "闪电说": ("闪电硕", "闪电説"),
    "DeepSeek": ("deep seek", "Deep seek", "深度求索"),
    "DashScope": ("dash scope", "Dash scope", "百炼"),
}

TYPELESS_CONTEXT_WORDS = (
    "对标", "参考", "产品", "功能", "悬浮窗", "静默学习", "识别错误",
    "输入", "输出", "自我迭代", "词典", "热词", "复刻",
)


def get_asr_context(words: list[str], max_length: int = 500) -> str:
    """Layer 1: build DashScope ASR context string."""
    if not words:
        return ""
    result = ""
    for word in canonical_hotwords(words):
        if len(result) + len(word) + 2 > max_length:
            break
        if result:
            result += ", "
        result += word
    return result


def fuzzy_correct(text: str, words: list[str]) -> str:
    """Layer 2: conservative post-ASR hotword correction.

    English hotwords are corrected only on token boundaries and known aliases.
    CJK fuzzy correction is intentionally strict to avoid corrupting normal text.
    """
    if not words or not text:
        return text
    result = text
    for hotword in canonical_hotwords(words):
        if hotword == "Typeless":
            result = _replace_typeless_context_aliases(result)
        result = _replace_aliases(result, hotword)
        if _is_ascii_word(hotword):
            result = _replace_ascii_phrase(result, hotword, hotword)
        elif _has_cjk(hotword) and hotword not in result:
            result = _replace_cjk_fuzzy(result, hotword)
    return result


def _replace_typeless_context_aliases(text: str) -> str:
    result = re.sub(r"(?<![A-Za-z0-9_])TABLES(?![A-Za-z0-9_])", "Typeless", text)
    if not any(word in result for word in TYPELESS_CONTEXT_WORDS):
        return result
    return re.sub(
        r"(?<![A-Za-z0-9_])(tables|table)(?![A-Za-z0-9_])",
        "Typeless",
        result,
        flags=re.IGNORECASE,
    )


def get_prompt_injection(words: list[str]) -> str:
    """Layer 3: build LLM prompt fragment to preserve hotwords."""
    clean_words = [(word or "").strip() for word in words if (word or "").strip()]
    if not clean_words:
        return ""
    items = ", ".join(f'"{word}"' for word in clean_words[:30])
    return f"请保留以下专有名词的原样写法，不要修改它们：{items}。"


def _replace_aliases(text: str, hotword: str) -> str:
    result = text
    for alias in HOTWORD_ALIASES.get(hotword, ()):
        if _is_ascii_phrase(alias):
            result = _replace_ascii_phrase(result, alias, hotword)
        else:
            result = result.replace(alias, hotword)
    return result


def _replace_ascii_phrase(text: str, phrase: str, replacement: str) -> str:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])" + re.escape(phrase) + r"(?![A-Za-z0-9_])",
        flags=re.IGNORECASE,
    )
    return pattern.sub(replacement, text)


def _replace_cjk_fuzzy(text: str, hotword: str) -> str:
    size = len(hotword)
    if size < 2:
        return text
    for i in range(len(text) - size + 1):
        sub = text[i:i + size]
        if not _has_cjk(sub):
            continue
        if _char_overlap(sub, hotword) >= 0.8:
            return text[:i] + hotword + text[i + size:]
    return text


def _char_overlap(s1: str, s2: str) -> float:
    """Compute character-level overlap ratio between two strings."""
    if not s1 or not s2:
        return 0.0
    set1 = set(s1)
    set2 = set(s2)
    if not set1:
        return 0.0
    return len(set1 & set2) / len(set1)


def canonical_hotwords(words: list[str]) -> list[str]:
    result: list[str] = []
    ascii_index: dict[str, int] = {}
    seen_other: set[str] = set()
    for word in words:
        word = (word or "").strip()
        if not word:
            continue
        if _is_ascii_word(word):
            key = word.lower()
            if key not in ascii_index:
                ascii_index[key] = len(result)
                result.append(word)
                continue
            current = result[ascii_index[key]]
            if _ascii_score(word) > _ascii_score(current):
                result[ascii_index[key]] = word
            continue
        if word in seen_other:
            continue
        seen_other.add(word)
        result.append(word)
    return result


def _ascii_score(value: str) -> tuple[int, int]:
    has_upper = int(any(ch.isupper() for ch in value))
    has_lower = int(any(ch.islower() for ch in value))
    return has_upper, has_lower


def _is_ascii_word(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*", value))


def _is_ascii_phrase(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_+\- ]+", value))


def _has_cjk(value: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in value)
