"""P0-3: Streaming session context priority test.

Proves that dynamic _streaming_context (updated by HotwordsManager)
takes priority over stale startup config when creating streaming sessions.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock


class FakeStreamingSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class AsrCascadeStreamingContextTests(unittest.TestCase):
    """P0-3: Dynamic streaming context must win over static config."""

    def setUp(self):
        # Minimal config with static aliyun.context set.
        self._config = {
            "aliyun": {
                "api_key": "sk-test",
                "context": "static_ctx",
            },
            "asr_streaming": {"enabled": True},
            "local": {"language": "zh"},
        }

    def _make_cascade(self):
        from infrastructure.asr import AsrCascade
        return AsrCascade(self._config)

    def test_dynamic_context_wins_over_static(self):
        """set_hotwords_context should take priority over startup config."""
        cascade = self._make_cascade()

        # Set dynamic context after construction.
        cascade.set_hotwords_context("dynamic_ctx")

        # Mock DashScopeStreamingASRSession to capture the context arg.
        mock_session_cls = MagicMock(return_value=FakeStreamingSession())
        with patch(
            "infrastructure.asr_streaming.DashScopeStreamingASRSession",
            mock_session_cls,
        ):
            session = cascade.create_streaming_session()

        self.assertIsNotNone(session)
        call_kwargs = mock_session_cls.call_args.kwargs
        self.assertEqual(
            call_kwargs.get("context"),
            "dynamic_ctx",
            "Dynamic context must take priority over static config context",
        )

    def test_static_context_fallback_when_no_dynamic(self):
        """Without set_hotwords_context, static config is the fallback."""
        cascade = self._make_cascade()

        mock_session_cls = MagicMock(return_value=FakeStreamingSession())
        with patch(
            "infrastructure.asr_streaming.DashScopeStreamingASRSession",
            mock_session_cls,
        ):
            session = cascade.create_streaming_session()

        self.assertIsNotNone(session)
        call_kwargs = mock_session_cls.call_args.kwargs
        self.assertEqual(
            call_kwargs.get("context"),
            "static_ctx",
            "Static config context should be used when no dynamic context set",
        )


if __name__ == "__main__":
    unittest.main()
