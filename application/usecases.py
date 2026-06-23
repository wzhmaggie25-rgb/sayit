"""Application use cases — bridge between UI requests and backend operations.

Each function is a self-contained use case that the UI (JS via pywebview bridge)
can call directly. All return serializable Python types (dict, list, str, int, bool).
"""
from __future__ import annotations
import logging
from typing import Optional

from infrastructure.ai_providers import build_providers, test_provider, AIProvider
from infrastructure.audio_capture import AudioCapture
from infrastructure.config_store import ConfigStore
from infrastructure.database import Database
from infrastructure.hotwords_manager import HotwordsManager
from infrastructure.version import VERSION
from domain.correction import (
    apply_rules,
    extract_dictionary_terms,
    learn_from_edit,
)

logger = logging.getLogger(__name__)


class UseCases:
    """Collection of use cases for the UI layer."""

    def __init__(self, db: Database, config: ConfigStore,
                 hotwords: HotwordsManager):
        self._db = db
        self._config = config
        self._hotwords = hotwords

    # ── History ─────────────────────────────────────────

    def get_history(self, search: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
        return self._db.get_history(search=search, limit=limit, offset=offset)

    def get_history_count(self, search: str = "") -> int:
        return self._db.count_history(search=search)

    def update_history_text(self, entry_id: int | str, text: str):
        entry = self._db.get_history_entry(entry_id)
        old_text = ""
        if entry:
            old_text = entry.get("final_text") or entry.get("refined_text") or entry.get("raw_text") or ""
        self._db.update_history_text(entry_id, text)
        if old_text and text and old_text.strip() != text.strip():
            try:
                rules, count = learn_from_edit(
                    original_text=old_text,
                    edited_text=text,
                    existing_rules=self._db.get_rules(active_only=False),
                    history_id=str(entry_id),
                )
                if count:
                    self._db.merge_rules(rules)
                for term in extract_dictionary_terms(old_text, text):
                    self._hotwords.add_word(term)
                logger.info(
                    "Manual history edit learned rules=%d entry=%s",
                    count, entry_id)
            except Exception as e:
                logger.warning("Manual history edit learning failed entry=%s err=%s", entry_id, e)

    def delete_history(self, entry_id: int | str):
        self._db.delete_history(entry_id)

    # ── Dictionary / Hotwords ────────────────────────────

    def get_dictionary(self) -> list[str]:
        return self._hotwords.get_words()

    def add_dictionary_word(self, word: str, pinyin: str = "") -> bool:
        return self._hotwords.add_word(word, pinyin)

    def remove_dictionary_word(self, word: str):
        self._hotwords.remove_word(word)

    def clear_dictionary(self):
        self._hotwords.clear()

    def get_dictionary_count(self) -> int:
        return self._hotwords.count()

    def import_dictionary(self, path: str) -> int:
        return self._hotwords.import_from_file(path)

    def export_dictionary(self, path: str):
        self._hotwords.export_to_file(path)

    # ── Correction Rules ─────────────────────────────────

    def get_rules(self, active_only: bool = False) -> list[dict]:
        return self._db.get_rules(active_only=active_only)

    def apply_rules_to_text(self, text: str) -> str:
        rules = self._db.get_rules(active_only=True)
        return apply_rules(text, rules)

    # ── Config ───────────────────────────────────────────

    def get_config_value(self, *keys: str, default=None):
        return self._config.get(*keys, default=default)

    def set_config_value(self, *keys_and_value):
        self._config.set(*keys_and_value)
        self._config.save()

    def get_all_config(self) -> dict:
        return self._config.get_all()

    def save_config(self):
        self._config.save()

    # ── Audio ────────────────────────────────────────────

    def detect_microphones(self) -> list[str]:
        return AudioCapture.detect_devices()

    # ── AI Provider Testing ──────────────────────────────

    def test_ai_provider(self, provider_id: str) -> dict:
        """Test an AI provider connection. Returns {ok: bool, message: str}."""
        providers = build_providers(self._config.get_all())
        for p in providers:
            if p.id == provider_id:
                ok, msg = test_provider(p)
                return {"ok": ok, "message": msg}
        return {"ok": False, "message": f"Provider '{provider_id}' not configured"}

    # ── Version ──────────────────────────────────────────

    def get_version(self) -> str:
        return VERSION

    # ── Update ───────────────────────────────────────────

    def check_update(self) -> dict:
        """Check GitHub for newer version. Returns {latest: str, current: str, has_update: bool, url: str}."""
        import httpx
        cfg = self._config.get_all()
        gh = cfg.get("update", {}).get("github", {})
        owner = gh.get("owner", "wzhmaggie25-rgb")
        repo = gh.get("repo", "sayit-release")

        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={"Accept": "application/vnd.github+json"})
                if resp.status_code == 200:
                    data = resp.json()
                    latest = (data.get("tag_name") or "").lstrip("v")
                    current = VERSION.lstrip("v")
                    has_update = self._compare_versions(latest, current) > 0
                    return {
                        "latest": latest,
                        "current": current,
                        "has_update": has_update,
                        "url": data.get("html_url", ""),
                    }
            return {"latest": "", "current": VERSION, "has_update": False,
                    "url": "", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"latest": "", "current": VERSION, "has_update": False,
                    "url": "", "error": str(e)[:100]}

    @staticmethod
    def _compare_versions(a: str, b: str) -> int:
        pa = [int(x) for x in a.split(".")]
        pb = [int(x) for x in b.split(".")]
        for i in range(max(len(pa), len(pb))):
            da = pa[i] if i < len(pa) else 0
            db = pb[i] if i < len(pb) else 0
            if da > db:
                return 1
            if da < db:
                return -1
        return 0
