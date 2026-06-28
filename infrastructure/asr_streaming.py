"""Streaming ASR sessions for Typeless-style realtime transcription.

Phase E (Round 9.4): Per-call executor for stop() — prevents a wedged
recognition.stop() from permanently poisoning subsequent finish()/abort()
calls. Each call creates a fresh ThreadPoolExecutor(max_workers=1) so a
hung SDK never leaks across sessions.
- finish() uses a single wall-clock budget: worker_join + stop + wait all
  share the caller's `timeout` budget, not fixed 3s+5s+timeout overhead.
- abort() wraps recognition.stop() in a bounded future so it cannot hang.
- No more shared ThreadPoolExecutor — every stop() call gets its own
  isolated executor, guaranteeing no cross-session poisoning.
"""
from __future__ import annotations

import concurrent.futures
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

    def _put_sentinel_safe(self):
        """Put the None sentinel into _audio_queue without blocking.

        Uses put_nowait; if the queue is full, drains one item to make room.
        This guarantees finish() cannot hang on a full queue with a dead worker.
        """
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            # Drain the oldest chunk to make room for the sentinel.
            # This is safe: we're terminating, lost audio is acceptable.
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(None)
            except (queue.Empty, queue.Full):
                # Queue is wedged — set _complete so finish() can proceed.
                self._complete.set()

    # ── Phase E: Per-call executor for stop() — no cross-session poisoning ──

    def _exec_stop(self, timeout: float) -> None:
        """Call recognition.stop() in a fresh executor with bounded timeout.

        Each call creates its own ThreadPoolExecutor so a wedged stop()
        in one session cannot block another session's finish()/abort().
        """
        if self._recognition is None:
            return
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="asr-streaming-stop",
        )
        try:
            stop_future = executor.submit(self._recognition.stop)
            try:
                stop_future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                stop_future.cancel()
                raise
        finally:
            executor.shutdown(wait=False)

    def finish(self, timeout: float = 8.0) -> str:
        if not self._started or self._recognition is None:
            raise RuntimeError("DashScope streaming ASR was not started")
        deadline = time.time() + timeout

        # Safe sentinel: never blocking put(None) — the core P0-2 fix.
        self._put_sentinel_safe()

        # Worker join — capped by remaining budget, not fixed 3s.
        if self._worker:
            remaining = max(0.0, deadline - time.time())
            self._worker.join(timeout=min(remaining, timeout))

        # recognition.stop() via per-call executor.
        remaining = max(0.0, deadline - time.time())
        try:
            self._exec_stop(timeout=remaining)
        except concurrent.futures.TimeoutError:
            # stop() didn't complete within remaining budget — treat as error
            if not self._error:
                self._error = "recognition.stop() timed out"
            self._complete.set()
        except Exception as e:
            self._error = str(e)
            self._complete.set()

        # Final wait for _complete event — capped by remaining budget.
        remaining = max(0.0, deadline - time.time())
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

    # ── Phase E: Per-call executor for abort too ──────────────────────────

    def abort(self):
        # Send sentinel so worker thread terminates.
        try:
            self._audio_queue.put_nowait(None)
        except Exception:
            pass
        # recognition.stop() via per-call executor with bounded timeout.
        # This prevents abort() from hanging when the SDK wedges, without
        # sharing an executor that another session might have poisoned.
        try:
            self._exec_stop(timeout=3.0)
        except (concurrent.futures.TimeoutError, Exception):
            pass