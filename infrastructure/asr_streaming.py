"""Streaming ASR sessions for Typeless-style realtime transcription."""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class DashScopeStreamingASRSession:
    """DashScope Recognition.start/send_audio_frame/stop wrapper."""

    def __init__(
        self,
        api_key: str,
        model: str = "fun-asr-realtime",
        sample_rate: int = 16000,
        ws_endpoint: str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        vocabulary_id: str = "",
        context: str = "",
        language: str = "zh",
        max_sentence_silence: int = 1300,
        event_callback: Optional[Callable[[str, dict], None]] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.sample_rate = sample_rate
        self.ws_endpoint = ws_endpoint
        self.vocabulary_id = vocabulary_id or ""
        self.context = context or ""
        self.language = language or "zh"
        self.max_sentence_silence = max_sentence_silence
        self._event_callback = event_callback
        self._audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=200)
        self._sentences: list[str] = []
        self._latest_partial = ""
        self._error: Optional[str] = None
        self._complete = threading.Event()
        self._started = False
        self._closed = False
        self._worker: Optional[threading.Thread] = None
        self._recognition = None

    def set_context(self, context: str):
        """Update Layer 1 ASR hotword context at runtime."""
        self.context = context or ""

    def _emit(self, kind: str, **payload):
        if self._event_callback:
            try:
                self._event_callback(kind, payload)
            except Exception:
                logger.debug("DashScope streaming event callback failed", exc_info=True)

    def start(self):
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        dashscope.api_key = self.api_key
        dashscope.base_websocket_api_url = self.ws_endpoint
        outer = self

        class _Callback(RecognitionCallback):
            def on_open(self) -> None:
                outer._emit("started", engine="aliyun_streaming", model=outer.model)

            def on_event(self, result: RecognitionResult) -> None:
                try:
                    sentence = result.get_sentence()
                except Exception:
                    sentence = None
                if not isinstance(sentence, dict):
                    return
                text = (sentence.get("text") or "").strip()
                if not text:
                    return
                outer._latest_partial = text
                try:
                    is_end = bool(RecognitionResult.is_sentence_end(sentence))
                except Exception:
                    is_end = bool(sentence.get("sentence_end"))
                if is_end:
                    outer._sentences.append(text)
                    outer._emit("sentence_end", text=text, engine="aliyun_streaming")
                else:
                    outer._emit("partial", text=text, engine="aliyun_streaming")

            def on_complete(self) -> None:
                outer._complete.set()
                outer._emit("complete", engine="aliyun_streaming")

            def on_error(self, result) -> None:
                msg = getattr(result, "message", None) or str(result)
                outer._error = msg
                outer._complete.set()
                outer._emit("error", message=msg, engine="aliyun_streaming")

            def on_close(self) -> None:
                outer._closed = True

        self._recognition = Recognition(
            model=self.model,
            format="pcm",
            sample_rate=self.sample_rate,
            language_hints=[self.language] if self.language else None,
            max_sentence_silence=self.max_sentence_silence,
            heartbeat=True,
            context=self.context or None,
            callback=_Callback(),
        )
        kwargs = {}
        if self.vocabulary_id:
            kwargs["phrase_id"] = self.vocabulary_id
        self._recognition.start(**kwargs)
        self._started = True
        self._worker = threading.Thread(target=self._send_loop, name="dashscope-streaming-asr", daemon=True)
        self._worker.start()
        logger.info("[ASR-STREAM] started model=%s vocabulary_id=%r context=%r", self.model, self.vocabulary_id, self.context[:80] if self.context else "")

    def enqueue_audio(self, pcm_chunk: bytes):
        if not self._started or self._closed or not pcm_chunk:
            return
        try:
            self._audio_queue.put_nowait(pcm_chunk)
        except queue.Full:
            self._emit("warning", message="streaming audio backlog full", engine="aliyun_streaming")
            logger.warning("[ASR-STREAM] audio backlog full, dropping chunk")

    def _send_loop(self):
        assert self._recognition is not None
        while True:
            chunk = self._audio_queue.get()
            if chunk is None:
                break
            try:
                self._recognition.send_audio_frame(chunk)
            except Exception as e:
                self._error = str(e)
                self._complete.set()
                self._emit("error", message=str(e), engine="aliyun_streaming")
                break

    def finish(self, timeout: float = 45.0) -> str:
        if not self._started or self._recognition is None:
            raise RuntimeError("DashScope streaming ASR was not started")
        self._audio_queue.put(None)
        if self._worker:
            self._worker.join(timeout=10.0)
        try:
            self._recognition.stop()
        except Exception as e:
            self._error = str(e)
        deadline = time.time() + timeout
        while not self._complete.is_set() and time.time() < deadline:
            time.sleep(0.05)
        if self._error:
            raise RuntimeError(self._error)
        if not self._complete.is_set():
            raise TimeoutError(f"DashScope streaming ASR final result timed out after {timeout}s")
        text = "".join(self._sentences).strip() or self._latest_partial.strip()
        if not text:
            raise RuntimeError("DashScope streaming ASR returned empty text")
        logger.info("[ASR-STREAM] final text(len=%d): %r", len(text), text[:200])
        return text

    def abort(self):
        try:
            self._audio_queue.put_nowait(None)
        except Exception:
            pass
        try:
            if self._recognition is not None:
                self._recognition.stop()
        except Exception:
            pass
