"""Path utilities — app data directory, model directory, log directory."""
from __future__ import annotations
import os
import sys


def _get_appdata_dir() -> str:
    """Get %APPDATA%/Sayit directory, creating if needed."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    path = os.path.join(base, "Sayit")
    os.makedirs(path, exist_ok=True)
    return path


def _get_project_root() -> str:
    """Get the directory containing main.py."""
    import __main__
    if hasattr(__main__, "__file__"):
        return os.path.dirname(os.path.abspath(__main__.__file__))
    return os.path.dirname(os.path.abspath(__file__))


PROJECT_ROOT = _get_project_root()
APP_DATA_DIR = _get_appdata_dir()


def config_path() -> str:
    """Path to config.json in app data directory."""
    # Prefer project root for development, appdata for installed
    local = os.path.join(PROJECT_ROOT, "config.json")
    if os.path.exists(local):
        return local
    return os.path.join(APP_DATA_DIR, "config.json")


def database_path() -> str:
    return os.path.join(APP_DATA_DIR, "sayit.db")


def log_path() -> str:
    return os.path.join(APP_DATA_DIR, "sayit.log")


def models_dir() -> str:
    return os.path.join(PROJECT_ROOT, "models")


def recordings_dir() -> str:
    path = os.path.join(APP_DATA_DIR, "recordings")
    os.makedirs(path, exist_ok=True)
    return path


def hotwords_txt_path() -> str:
    return os.path.join(APP_DATA_DIR, "hotwords.txt")


def hotwords_json_path() -> str:
    return os.path.join(APP_DATA_DIR, "hotwords.json")
