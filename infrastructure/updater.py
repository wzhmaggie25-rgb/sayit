"""GitHub Release auto-updater — checks for new versions, downloads .zip releases."""
from __future__ import annotations
import json
import logging
import os
import sys
import tempfile
import zipfile
from typing import Optional

import httpx

from infrastructure.config_store import ConfigStore
from infrastructure.version import VERSION
from infrastructure.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


def check_update() -> Optional[dict]:
    """Check GitHub for newer version.

    Returns dict with {latest, current, has_update, url, changelog} or None on failure.
    """
    config = ConfigStore()
    gh = config.get("update", "github", default={})
    owner = gh.get("owner", "wzhmaggie25-rgb")
    repo = gh.get("repo", "sayit-release")

    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(
                url, headers={"Accept": "application/vnd.github+json"})
            if resp.status_code != 200:
                logger.warning("Update check: HTTP %d", resp.status_code)
                return None
            data = resp.json()
    except Exception as e:
        logger.warning("Update check failed: %s", e)
        return None

    latest = (data.get("tag_name") or "").lstrip("v")
    current = VERSION.lstrip("v")
    has_update = _cmp_ver(latest, current) > 0

    return {
        "latest": latest,
        "current": current,
        "has_update": has_update,
        "url": data.get("html_url", ""),
        "changelog": data.get("body", "")[:500],
        "assets": [
            {"name": a.get("name", ""), "url": a.get("browser_download_url", "")}
            for a in data.get("assets", [])
        ],
    }


def download_and_install(download_url: str) -> bool:
    """Download a .zip release and extract into the current install directory.

    Returns True on success.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name

        # Download
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            with open(tmp_path, "wb") as f:
                with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    for chunk in resp.iter_bytes(65536):
                        f.write(chunk)

        # Extract to project root
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(PROJECT_ROOT)

        os.unlink(tmp_path)
        logger.info("Update installed successfully from %s", download_url)
        return True
    except Exception as e:
        logger.error("Update install failed: %s", e)
        return False


def _cmp_ver(a: str, b: str) -> int:
    """Compare two version strings. >0 if a > b."""
    pa = [int(x) for x in a.split(".")]
    pb = [int(x) for x in b.split(".")]
    for i in range(max(len(pa), len(pb))):
        da = pa[i] if i < len(pa) else 0
        db = pb[i] if i < len(pb) else 0
        if da > db:
            return 1
        if da < db:
            return -1
    return 0
