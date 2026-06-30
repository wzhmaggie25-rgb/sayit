"""Focused regression tests for the empty-normalized-input AI guard.

Practical-incident P0: normalization could reduce ASR text to empty, yet the AI
provider was still called and invented text. These prove the provider is never
called for empty / whitespace / filler-only normalized input.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

import infrastructure.corrector as corrector_mod
from infrastructure.corrector import correct_text, normalize_text


class EmptyNormalizedInputGuardTests(unittest.TestCase):
    """correct_text must never call an AI provider on empty normalized input."""

    def _providers(self):
        prov = MagicMock()
        prov.id = "test"
        prov.model = "test-model"
        prov.endpoint = "http://x"
        prov.enabled = True
        prov.priority = 1
        return [prov]

    def _run(self, raw_text, **kw):
        providers = kw.pop("providers", self._providers())
        with patch.object(corrector_mod, "call_provider") as mock_call, \
             patch.object(corrector_mod, "ConfigStore") as mock_cfg:
            mock_cfg.return_value.get_all.return_value = {}
            mock_cfg.return_value.get.return_value = ""
            result = correct_text(raw_text, providers=providers, **kw)
        return result, mock_call

    def test_empty_input_does_not_call_provider(self):
        result, mock_call = self._run("")
        text, pid, model = result
        self.assertEqual(text, "")
        self.assertIsNone(pid)
        self.assertIsNone(model)
        mock_call.assert_not_called()

    def test_whitespace_only_input_does_not_call_provider(self):
        result, mock_call = self._run("   \n\t  ")
        text, pid, _ = result
        self.assertEqual(text.strip(), "")
        self.assertIsNone(pid)
        mock_call.assert_not_called()

    def test_filler_only_input_normalizes_to_empty_and_skips_provider(self):
        # Filler-only input is non-empty raw, but normalization removes fillers.
        self.assertEqual(normalize_text("嗯嗯嗯"), "")
        result, mock_call = self._run("嗯嗯嗯")
        text, pid, _ = result
        self.assertEqual(text, "")
        self.assertIsNone(pid)
        mock_call.assert_not_called()

    def test_real_text_still_calls_provider(self):
        result, mock_call = self._run("打开豆包助手")
        mock_call.assert_called_once()
        # Provider was invoked with the normalized non-empty text.
        called_text = mock_call.call_args.args[2]
        self.assertTrue(called_text.strip())


if __name__ == "__main__":
    unittest.main()
