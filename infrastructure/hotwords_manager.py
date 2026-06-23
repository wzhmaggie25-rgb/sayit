"""Hotwords manager: dictionary CRUD plus three-layer ASR/AI hotword support."""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from domain.hotwords import (
    canonical_hotwords,
    get_asr_context,
    fuzzy_correct,
    get_prompt_injection,
)
from infrastructure.config_store import ConfigStore
from infrastructure.database import Database

logger = logging.getLogger(__name__)

CORE_HOTWORDS = ("Sayit", "Typeless", "闪电说", "DeepSeek", "DashScope")


class HotwordsManager:
    """Manages personal dictionary and three-layer hotword injection."""

    def __init__(self):
        self._db = Database()
        self._asr_engine = None
        self.ensure_core_hotwords()

    def set_asr_engine(self, asr_cascade):
        """Set the ASR cascade engine for Layer 1 context updates."""
        self._asr_engine = asr_cascade
        self._sync_to_asr()

    def ensure_core_hotwords(self) -> int:
        """Ensure built-in product/provider names are present in the dictionary."""
        existing = set(self._db.get_dictionary())
        added = 0
        for word in CORE_HOTWORDS:
            if word not in existing and self._db.add_dictionary_word(word):
                added += 1
        if added:
            logger.info("HotwordsManager: seeded %d core hotwords", added)
        return added

    def get_words(self) -> list[str]:
        return self._db.get_dictionary()

    def add_word(self, word: str, pinyin: str = "") -> bool:
        ok = self._db.add_dictionary_word(word, pinyin)
        if ok:
            self._sync_to_asr()
        return ok

    def remove_word(self, word: str):
        self._db.remove_dictionary_word(word)
        self._sync_to_asr()

    def clear(self):
        self._db.clear_dictionary()
        self._sync_to_asr()

    def count(self) -> int:
        return len(self._db.get_dictionary())

    def import_from_file(self, path: str) -> int:
        """Import words from a text file (one word per line) or JSON array."""
        if not os.path.exists(path):
            return 0
        count = 0
        try:
            if path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                words = data if isinstance(data, list) else list(data.keys())
            else:
                with open(path, "r", encoding="utf-8") as f:
                    words = [line.strip() for line in f if line.strip()]
            for word in words:
                if self.add_word(str(word)):
                    count += 1
        except Exception as e:
            logger.error("HotwordsManager: import failed: %s", e)
        return count

    def export_to_file(self, path: str):
        """Export words to a file (JSON or TXT based on extension)."""
        words = self.get_words()
        if path.endswith(".json"):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(words, f, ensure_ascii=False, indent=2)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(words))

    def get_layer1_context(self) -> str:
        """Layer 1: build ASR context for DashScope."""
        return get_asr_context(self.get_words())

    def apply_layer2_correction(self, text: str) -> str:
        """Layer 2: local hotword correction on ASR output."""
        return fuzzy_correct(text, self.get_words())

    def get_layer3_prompt(self) -> str:
        """Layer 3: LLM prompt to preserve hotwords."""
        return get_prompt_injection(self.get_words())

    def get_full_prompt_injection(self) -> str:
        """Get the combined Layer 3 prompt for use in AI correction."""
        words = self.get_words()
        if not words:
            return ""
        items = ", ".join(f'"{w}"' for w in words[:30])
        return f"\n\n请保留以下专有名词的原样写法，不要修改它们：{items}。"

    def sync_aliyun_vocabulary(self, config: Optional[ConfigStore] = None) -> dict:
        """Create/update DashScope vocabulary and store the active vocabulary_id."""
        cfg_store = config or ConfigStore()
        cfg = cfg_store.get_all()
        aliyun = cfg.get("aliyun", {})
        api_key = (aliyun.get("api_key") or "").strip()
        if not api_key:
            return {"ok": False, "error": "aliyun.api_key is empty"}

        words = canonical_hotwords(self.get_words())
        if not words:
            return {"ok": False, "error": "dictionary is empty"}

        target_model = (
            aliyun.get("vocabulary_target_model")
            or aliyun.get("asr_model")
            or "fun-asr-realtime"
        )
        prefix = self._normalize_vocabulary_prefix(
            aliyun.get("vocabulary_prefix") or "sayithot"
        )
        vocabulary_id = (aliyun.get("vocabulary_id") or "").strip()
        vocabulary = [self._to_aliyun_vocabulary_item(word) for word in words[:1000]]

        try:
            from dashscope.audio.asr import VocabularyService
            service = VocabularyService(api_key=api_key)
            if vocabulary_id:
                service.update_vocabulary(vocabulary_id=vocabulary_id, vocabulary=vocabulary)
                action = "update"
            else:
                vocabulary_id = service.create_vocabulary(
                    target_model=target_model,
                    prefix=prefix,
                    vocabulary=vocabulary,
                )
                cfg_store.set("aliyun", "vocabulary_id", vocabulary_id)
                cfg_store.save()
                action = "create"

            self._sync_to_asr(vocabulary_id=vocabulary_id)
            logger.info(
                "HotwordsManager: Aliyun vocabulary %s ok id=%s words=%d target_model=%s",
                action, vocabulary_id, len(vocabulary), target_model)
            return {
                "ok": True,
                "action": action,
                "vocabulary_id": vocabulary_id,
                "word_count": len(vocabulary),
                "target_model": target_model,
                "prefix": prefix,
            }
        except Exception as e:
            logger.exception("HotwordsManager: Aliyun vocabulary sync failed")
            return {"ok": False, "error": str(e), "vocabulary_id": vocabulary_id}

    def _sync_to_asr(self, vocabulary_id: str | None = None):
        """Sync dictionary changes to the ASR engine."""
        if self._asr_engine is None:
            return
        try:
            context = self.get_layer1_context()
            self._asr_engine.set_hotwords_context(context)
            if vocabulary_id is None:
                vocabulary_id = ConfigStore().get("aliyun", "vocabulary_id", "")
            if hasattr(self._asr_engine, "set_hotwords_vocabulary_id"):
                self._asr_engine.set_hotwords_vocabulary_id(vocabulary_id or "")
            logger.info(
                "HotwordsManager: synced %d words to ASR context, vocabulary_id=%r",
                self.count(), vocabulary_id or "")
        except Exception as e:
            logger.warning("HotwordsManager: sync to ASR failed: %s", e)

    @staticmethod
    def _to_aliyun_vocabulary_item(word: str) -> dict:
        lang = "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in word) else "en"
        return {"text": word, "weight": 4, "lang": lang}

    @staticmethod
    def _normalize_vocabulary_prefix(value: str) -> str:
        prefix = "".join(ch for ch in value.lower() if ch.isdigit() or ("a" <= ch <= "z"))
        return prefix[:9] or "sayithot"
