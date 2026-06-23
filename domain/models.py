"""Pure domain models for Sayit — no external dependencies."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class RecordingState(Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    CORRECTING = "correcting"
    INJECTING = "injecting"
    DONE = "done"
    ERROR = "error"


class CorrectionStyle(Enum):
    OFF = "off"
    LIGHT = "light"
    STRUCTURED = "structured"


class TextPostProcess:
    """Text post-processing config."""
    punctuation: bool = True
    formatting: bool = False
    style: str = "light"  # off | light | structured


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    format: str = "pcm_s16le"
    gain_enabled: bool = True
    gain_multiplier: float = 2.0


@dataclass
class ASRConfig:
    primary_engine: str = "aliyun"
    fallback_enabled: bool = True
    fallback_order: list[str] = field(default_factory=lambda: ["aliyun", "volcengine", "onnx"])
    local_language: str = "zh"
    local_itn: bool = True


@dataclass
class Recording:
    """A recording session."""
    id: str
    pcm_data: bytes = field(default_factory=bytes, repr=False)
    duration_seconds: float = 0.0
    sample_rate: int = 16000
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Transcription:
    """ASR transcription result."""
    raw_text: str
    engine: str  # aliyun | volcengine | onnx
    confidence: float = 0.0
    latency_ms: float = 0.0


@dataclass
class CorrectedText:
    """Result after AI correction pipeline."""
    raw_text: str
    normalized_text: str = ""
    refined_text: str = ""
    final_text: str = ""
    provider: str = ""  # which AI provider was used
    tasks_applied: list[str] = field(default_factory=list)  # correction, summary, keywords, translate


@dataclass
class HistoryEntry:
    """A saved transcription with metadata."""
    id: int
    raw_text: str
    refined_text: str = ""
    normalized_text: str = ""
    final_text: str = ""
    app_name: str = ""
    app_exe: str = ""
    window_title: str = ""
    window_class: str = ""
    duration: float = 0.0
    language: str = "zh-CN"
    language_label: str = "中文"
    pasted: bool = False
    error_msg: str = ""
    created_at: str = ""

    @property
    def display_date(self) -> str:
        return self.created_at[:16] if self.created_at else ""

    @property
    def display_duration(self) -> str:
        m, s = divmod(int(self.duration), 60)
        return f"{m:02d}:{s:02d}"


@dataclass
class CorrectionRule:
    """A learned correction rule."""
    id: str
    pattern: str
    replacement: str
    source_type: str = "user_edit"  # user_edit | manual
    source_history_id: Optional[str] = None
    confidence: float = 0.4
    match_count: int = 1
    apply_count: int = 0
    is_active: bool = True
    is_regex: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass
class DictWord:
    """A custom dictionary word for improved ASR accuracy."""
    word: str
    pinyin: str = ""
    added_at: str = ""


@dataclass
class AppStrategy:
    """Injection strategy for a specific application."""
    process_name: str
    strategy: str  # uia | send_input | clipboard
    terminal: bool = False
    uia_unreliable: bool = False
