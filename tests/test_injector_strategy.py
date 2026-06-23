from __future__ import annotations

import unittest

from infrastructure.injector import Injector


def make_context(proc: str, app_type: str = "native_app",
                 page_url: str = "", domain: str = "",
                 editable: bool = True) -> dict:
    browser_context = None
    if app_type == "web_browser":
        browser_context = {
            "page_title": "Probe",
            "page_url": page_url,
            "domain": domain,
        }
    return {
        "active_application": {
            "app_name": proc,
            "app_identifier": proc,
            "app_type": app_type,
            "browser_context": browser_context,
        },
        "text_insertion_point": {
            "input_capabilities": {
                "is_editable": editable,
            },
        },
    }


class InjectorStrategyTests(unittest.TestCase):
    def test_chrome_regular_input_uses_uia(self):
        injector = Injector()
        context = make_context(
            "chrome.exe",
            app_type="web_browser",
            page_url="https://example.com/editor",
            domain="example.com",
        )

        strategy = injector._strategy_for_context("chrome.exe", "Chrome_WidgetWin_1", context)

        self.assertEqual(strategy, "uia")

    def test_google_docs_url_blacklist_uses_clipboard(self):
        injector = Injector()
        context = make_context(
            "chrome.exe",
            app_type="web_browser",
            page_url="https://docs.google.com/document/d/abc123/edit",
            domain="docs.google.com",
        )

        strategy = injector._strategy_for_context("chrome.exe", "Chrome_WidgetWin_1", context)

        self.assertEqual(strategy, "clipboard")

    def test_word_typeless_blacklist_uses_clipboard(self):
        injector = Injector()
        context = make_context("winword.exe")

        strategy = injector._strategy_for_context("winword.exe", "OpusApp", context)

        self.assertEqual(strategy, "clipboard")

    def test_windows_terminal_processes_use_clipboard(self):
        injector = Injector()

        for proc in (
            "windowsterminal.exe",
            "wt.exe",
            "cmd.exe",
            "powershell.exe",
            "pwsh.exe",
            "conhost.exe",
        ):
            with self.subTest(proc=proc):
                strategy = injector._strategy_for_context(
                    proc, "CASCADIA_HOSTING_WINDOW_CLASS", make_context(proc))

                self.assertEqual(strategy, "clipboard_terminal")

    def test_terminal_window_class_uses_clipboard(self):
        injector = Injector()

        strategy = injector._strategy_for_context(
            "unknown.exe", "ConsoleWindowClass", make_context("unknown.exe"))

        self.assertEqual(strategy, "clipboard_terminal")


if __name__ == "__main__":
    unittest.main()
