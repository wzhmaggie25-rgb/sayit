"""Autostart management — Windows registry Run key."""
from __future__ import annotations
import os
import sys
import winreg


APP_NAME = "Sayit"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_enabled() -> bool:
    """Check if autostart is enabled in the registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def enable():
    """Add Sayit to Windows startup registry."""
    try:
        exe_path = sys.executable
        # If running from script, use the main.py path
        if not exe_path.endswith(".exe"):
            exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
        else:
            exe_path = f'"{exe_path}"'

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
        return True
    except OSError as e:
        print(f"Failed to enable autostart: {e}")
        return False


def disable():
    """Remove Sayit from Windows startup registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return True
    except OSError as e:
        print(f"Failed to disable autostart: {e}")
        return False
