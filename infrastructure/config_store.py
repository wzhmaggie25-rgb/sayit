"""Config store — thread-safe JSON config with mtime-based hot reload."""
from __future__ import annotations
import json
import logging
import os
import threading
from typing import Any, Optional

from infrastructure.paths import config_path, APP_DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "update": {
        "github": {"owner": "wzhmaggie25-rgb", "repo": "sayit-release",
                   "version_asset": "version.json", "exe_asset": "sayit.zip"},
        "channel": "stable",
        "auto_check": True,
    },
    "float_window_enabled": False,
    "injection_mode": "auto",
    "hotkey": "RAlt",
    "history_retention": {"max_count": 1000, "max_days": 90},
    "audio": {
        "channels": 1, "format": "pcm_s16le",
        "gain_enabled": True, "gain_multiplier": 2.0,
        # Noise gate: chunks whose RMS falls below this normalized threshold are
        # zeroed. The practical incident showed 0.015 was too high relative to a
        # captured RMS of ~0.005, zeroing ~97% of samples. The default is now
        # conservative (0.0); runtime also auto-clamps an over-aggressive gate.
        "noise_gate_threshold": 0.0,
        "dump_last_wav": True,
    },
    "asr_engine": "aliyun",
    "asr_fallback": {
        "enable": True,
        "order": ["aliyun", "volcengine", "onnx"],
        "onnx_model_dir": "",
    },
    "local": {"language": "zh", "itn": True},
    "aliyun": {
        "api_key": "",
        "endpoint": "https://dashscope.aliyuncs.com/api/v1",
        "ws_endpoint": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        "asr_model": "fun-asr-realtime",
        "correction_model": "qwen-flash",        # qwen-flash 是北京地域稳定别名，自动指向最新版
        "context": "",
        "vocabulary_id": "",                      # Phase 2 热词，空=不启用
        "vocabulary_prefix": "sayithot",
        "vocabulary_target_model": "fun-asr-realtime",
    },
    "volcengine": {
        "asr": {
            "app_id": "", "access_token": "", "cluster": "",
            "resource_id": "volc.seedasr.sauc.duration",
            "endpoint": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream",
        },
        "ai": {
            "endpoint": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "",
            "correction_model": "doubao-seed-2-0-mini-260428",  # 以火山控制台确切日期版为准
        },
    },
    "deepseek": {
        "api_key": "",
        "correction_model": "deepseek-v4-flash",  # 注意 chat/reasoner 2026-07-24 停用
    },
    "enable_correction": True,
    "enable_structuring": True,
    "organize_level": "light",
    "remove_trailing_period": False,
    "correction_prompt": "",
    "structuring_prompt": "",
    "system_prompt": "",
    "text_postprocess": {"punctuation": True, "formatting": False, "style": "light"},
    "silent_learning": True,
    "copy_result_to_clipboard": False,
    "asr_total_budget_s": 30.0,  # Phase G: total ASR budget (streaming + batch), 0 = unlimited
    "ai_providers": [],
    "onboarding": {"version": 1, "completed": False},
}


class ConfigStore:
    """Thread-safe singleton for configuration management."""

    _instance: Optional["ConfigStore"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ConfigStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._data: dict = {}
        self._rw_lock = threading.RLock()
        self._mtime: float = 0.0
        self._config_path = config_path()
        self._load()

    @staticmethod
    def _apply_env_overrides(data: dict):
        """Override config values from environment variables (highest priority).

        This allows users to configure API keys via env vars instead of
        editing config.json — critical for open-source safety.
        Priority chain:  env var > config.json > built-in defaults.
        """
        env_map = {
            "SAYIT_ALIYUN_API_KEY":            ["aliyun", "api_key"],
            "SAYIT_VOLCENGINE_ASR_ACCESS_TOKEN": ["volcengine", "asr", "access_token"],
            "SAYIT_VOLCENGINE_ASR_APP_ID":     ["volcengine", "asr", "app_id"],
            "SAYIT_VOLCENGINE_AI_API_KEY":     ["volcengine", "ai", "api_key"],
            "SAYIT_DEEPSEEK_API_KEY":          ["deepseek", "api_key"],
        }
        for env_var, keys in env_map.items():
            val = os.environ.get(env_var)
            if val:
                node = data
                for key in keys[:-1]:
                    node = node.setdefault(key, {})
                node[keys[-1]] = val

    def _load(self):
        """Load config from JSON file, merging with defaults for missing keys."""
        with self._rw_lock:
            data = dict(DEFAULT_CONFIG)
            try:
                if os.path.exists(self._config_path):
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        user_data = json.load(f)
                    self._deep_merge(data, user_data)
                    self._mtime = os.path.getmtime(self._config_path)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load config: %s, using defaults", e)
            self._apply_env_overrides(data)
            self._data = data

    def reload_if_changed(self) -> bool:
        """Check mtime and reload if file changed. Returns True if reloaded."""
        try:
            if os.path.exists(self._config_path):
                new_mtime = os.path.getmtime(self._config_path)
                if new_mtime > self._mtime:
                    self._load()
                    logger.info("Config hot-reloaded")
                    return True
        except OSError:
            pass
        return False

    def save(self, _strip_keys=False):
        """Save current config to JSON file."""
        with self._rw_lock:
            try:
                data = self._data
                if _strip_keys:
                    data = self._strip_api_keys(data)
                os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
                with open(self._config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self._mtime = os.path.getmtime(self._config_path)
            except OSError as e:
                logger.error("Failed to save config: %s", e)

    @staticmethod
    def _strip_api_keys(data: dict) -> dict:
        """Return a copy with all api_key/token fields emptied (disk-safe)."""
        import copy
        d = copy.deepcopy(data)
        def _walk(obj):
            if not isinstance(obj, dict):
                return
            for k, v in list(obj.items()):
                if isinstance(v, str) and ("key" in k.lower() or "token" in k.lower()):
                    obj[k] = ""
                elif isinstance(v, dict):
                    _walk(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            _walk(item)
        _walk(d)
        return d

    def get(self, *keys: str) -> Any:
        """Get a nested config value by key path.

        The last argument is the default if value not found.
        E.g. config.get('audio', 'gain_multiplier', 6.0) → 6.0 when missing.
        """
        if len(keys) < 1:
            return None
        *path, default = keys
        with self._rw_lock:
            node = self._data
            for key in path:
                if isinstance(node, dict):
                    node = node.get(key, {})
                else:
                    return default
            return node if node != {} else default

    def set(self, *keys_and_value: Any):
        """Set a nested config value. Last arg is the value.
        E.g. config.set('audio', 'gain_multiplier', 8.0)
        """
        value = keys_and_value[-1]
        keys = keys_and_value[:-1]
        with self._rw_lock:
            node = self._data
            for key in keys[:-1]:
                if key not in node:
                    node[key] = {}
                node = node[key]
            node[keys[-1]] = value

    def get_all(self) -> dict:
        """Return a shallow copy of the full config dict."""
        with self._rw_lock:
            return dict(self._data)

    @staticmethod
    def _deep_merge(base: dict, override: dict):
        """Recursively merge override into base in-place."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigStore._deep_merge(base[key], value)
            else:
                base[key] = value
