# ── VolcEngine ASR v3 (ByteDance WebSocket) ───────────────────

import json
import struct
import uuid
import gzip
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def _pcm_stats(pcm: bytes) -> str:
    """Short PCM summary for logging."""
    import math
    if not pcm:
        return "0B (0s)"
    samples = len(pcm) // 2
    rms = math.sqrt(sum(int.from_bytes(pcm[i:i+2], 'little', signed=True)**2 
                        for i in range(0, len(pcm)-1, 2)) / max(samples, 1)) / 32768
    dur = samples / 16000
    return f"{len(pcm)}B ({dur:.1f}s) RMS={rms:.3f}"

DEFAULT_VOLCENGINE_V3_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"


class VolcengineASR:
    """Volcano Engine v3 WebSocket streaming speech recognition."""

    VERSION = 0b0001
    HEADER_SIZE = 1  # ×4 bytes = 4
    MSG_FULL_REQUEST = 0b0001
    MSG_AUDIO_ONLY = 0b0010
    MSG_SERVER_RESP = 0b1001
    MSG_ERROR = 0b1111
    SERIAL_JSON = 0b0001
    SERIAL_NONE = 0b0000
    COMPRESS_GZIP = 0b0001
    COMPRESS_NONE = 0b0000
    FLAG_SEQ_POS = 0b0001
    FLAG_LAST_PACK = 0b0010
    
    def __init__(self, api_key: str, resource_id: str = "volc.seedasr.sauc.duration",
                 endpoint: str = DEFAULT_VOLCENGINE_V3_ENDPOINT,
                 hotwords: list[str] | None = None):
        self.api_key = api_key
        self.resource_id = resource_id
        self.endpoint = self._normalize_endpoint(endpoint)
        self.hotwords = hotwords or []

    def set_hotwords(self, words: list[str]):
        self.hotwords = words or []

    def set_context(self, context: str):
        self.hotwords = [
            word.strip()
            for word in (context or "").split(",")
            if word.strip()
        ]

def transcribe(self, pcm_bytes: bytes, remaining: float | None = None) -> str:
        import websocket
        logger.info("[VolcengineASR] PCM: %s", _pcm_stats(pcm_bytes))

        # Phase D: cap WebSocket timeout by remaining budget
        ws_timeout = 30.0
        if remaining is not None and remaining > 0:
            ws_timeout = min(ws_timeout, remaining)
        elif remaining is not None and remaining <= 0:
            raise RuntimeError(
                f"VolcengineASR v3 skipped — remaining budget exhausted "
                f"(remaining={remaining:.2f}s)")

        result_text = []
        error_msg = []
        ws = None

        try:
            # Connect with auth headers
            headers = {
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": self.resource_id,
                "X-Api-Request-Id": str(uuid.uuid4()),
            }
            # ── [VOLC-ASR-EP] diagnostic — log endpoint before WebSocket connect ──
            logger.info(
                "[VOLC-ASR-EP] engine=volcengine_v3 endpoint=%r scheme=%s host=%s",
                self.endpoint,
                urlparse(self.endpoint).scheme if self.endpoint else "N/A",
                urlparse(self.endpoint).hostname if self.endpoint else "N/A")
            # ── [VOLC-AUTH] diagnostic — check if api_key looks like an access_token ──
            if self.api_key and len(self.api_key) > 20 and "/" not in self.api_key and not self.api_key.startswith("AK"):
                logger.warning(
                    "[VOLC-AUTH] X-Api-Key=%r... does not look like a standard Volcengine API key "
                    "(expected format: 'AK...' or 'key@...'). "
                    "If you configured volcengine.asr.access_token, note that the v3 WebSocket API "
                    "requires an IAM API key, not the v1 HTTP access_token.",
                    self.api_key[:12])
            ws = websocket.create_connection(self.endpoint, header=headers,
                                              timeout=min(30.0, ws_timeout))
            
            # Send full client request
            request = {
                "user": {"uid": "sayit"},
                "audio": {
                    "format": "pcm",
                    "rate": 16000,
                    "bits": 16,
                    "channel": 1,
                    "language": "zh-CN",
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_itn": True,
                    "enable_punc": True,
                },
            }
            if self.hotwords:
                # VolcEngine v3 uses inline hotwords in corpus.context, not a vocabulary_id.
                request["request"]["corpus"] = {
                    "context": {
                        "hotwords": self.hotwords[:200],
                    }
                }
            logger.info(
                "[ASR-CALL-VOLC-HOTWORD] endpoint=%r resource_id=%r hotwords_count=%d hotwords=%r",
                self.endpoint, self.resource_id, len(self.hotwords), self.hotwords[:30])
            req_json = json.dumps(request, ensure_ascii=False)
            self._send_frame(ws, self.MSG_FULL_REQUEST, req_json, self.SERIAL_JSON, self.COMPRESS_GZIP)
            
            # Read server ack for full client request
            self._recv_frame(ws)
            
            # Send audio data in chunks (~200ms per chunk)
            chunk_size = 6400  # 200ms of 16kHz 16-bit mono = 6400 bytes
            seq = 1
            for i in range(0, len(pcm_bytes), chunk_size):
                chunk = pcm_bytes[i:i + chunk_size]
                is_last = i + chunk_size >= len(pcm_bytes)
                if is_last:
                    flags = self.FLAG_LAST_PACK | self.FLAG_SEQ_POS  # 0b0011: last + seq
                    self._send_frame(ws, self.MSG_AUDIO_ONLY, gzip.compress(chunk) if chunk else gzip.compress(b'\x00\x00'),
                                    self.SERIAL_NONE, self.COMPRESS_GZIP, flags=flags, seq=-1)
                else:
                    self._send_frame(ws, self.MSG_AUDIO_ONLY, gzip.compress(chunk),
                                    self.SERIAL_NONE, self.COMPRESS_GZIP, flags=self.FLAG_SEQ_POS, seq=seq)
                    seq += 1
            
            # Receive responses (with timeout)
            import time as _time
            deadline = _time.time() + min(15.0, ws_timeout)
            while _time.time() < deadline:
                resp = self._recv_frame(ws)
                if resp is None:
                    _time.sleep(0.1)
                    continue
                msg_type, payload = resp
                if msg_type == self.MSG_SERVER_RESP:
                    try:
                        data = json.loads(gzip.decompress(payload).decode("utf-8"))
                    except Exception:
                        data = json.loads(payload.decode("utf-8"))
                    text = data.get("result", {}).get("text", "")
                    if text:
                        result_text.append(text)
                    # Check for final result
                    utterances = data.get("result", {}).get("utterances", [])
                    if utterances and utterances[-1].get("definite"):
                        break
                    # For nostream, first result is final
                    if text:
                        break
                elif msg_type == self.MSG_ERROR:
                    try:
                        err_data = json.loads(payload.decode("utf-8")) if isinstance(payload, bytes) else payload
                    except Exception:
                        err_data = payload
                    error_msg.append(f"Server error: {err_data}")
                    break
                    
        except Exception as e:
            logger.warning("VolcengineASR error: %s", e)
            raise
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
        
        text = "".join(result_text).strip()
        if not text:
            if error_msg:
                raise RuntimeError(f"Volcengine ASR failed: {'; '.join(error_msg)}")
            raise RuntimeError("Volcengine returned empty text")
        
        logger.info("[VolcengineASR] text(len=%d): %s", len(text), repr(text[:200]))
        return text

    def _send_frame(self, ws, msg_type, payload, serial, compress, flags=0, seq=None):
        """Send a binary WebSocket frame."""
        # Build header (4 bytes)
        header = bytearray(4)
        header[0] = (self.VERSION << 4) | self.HEADER_SIZE
        header[1] = (msg_type << 4) | flags
        header[2] = (serial << 4) | compress
        
        # Compress if needed
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if compress == self.COMPRESS_GZIP:
            payload = gzip.compress(payload)
        
        # Build frame: header + [sequence] + payload_size + payload
        frame = bytes(header)
        if seq is not None:
            frame += struct.pack(">I", seq & 0xFFFFFFFF)
        frame += struct.pack(">I", len(payload))
        frame += payload
        
        ws.send(frame, opcode=2)  # Binary frame

    def _recv_frame(self, ws) -> tuple | None:
        """Receive and parse a binary WebSocket frame. Returns (msg_type, payload) or None."""
        import ssl, select
        try:
            opcode, data = ws.recv_data()
            if opcode != 2 or len(data) < 8:
                return None
            # Parse header
            msg_type = (data[1] >> 4) & 0x0F
            offset = 4
            if (data[1] & 0x0F) & 0x01:  # has sequence
                offset += 4
            payload_size = struct.unpack(">I", data[offset:offset + 4])[0]
            payload = data[offset + 4:offset + 4 + payload_size]
            return msg_type, payload
        except Exception as e:
            logger.warning("VolcengineASR recv error: %s", e)
            return None

    def _extract_text(self, data: dict) -> str:
        """Extract text from v3 response (legacy format)."""
        return data.get("result", {}).get("text", "")

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        endpoint = (endpoint or "").strip()
        if not endpoint:
            return DEFAULT_VOLCENGINE_V3_ENDPOINT
        parsed = urlparse(endpoint)
        if parsed.scheme in ("ws", "wss"):
            return endpoint
        logger.warning(
            "VolcengineASR: endpoint=%r is not WebSocket v3, using default %s",
            endpoint, DEFAULT_VOLCENGINE_V3_ENDPOINT)
        return DEFAULT_VOLCENGINE_V3_ENDPOINT
