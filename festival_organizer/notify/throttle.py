"""Once-per-version throttle marker for the update-reminder email."""

from __future__ import annotations

import json
from pathlib import Path

from festival_organizer import paths

_MARKER_FILENAME = "email-update-notified.json"


def _default_marker_path() -> Path:
    return paths.cache_dir() / _MARKER_FILENAME


def already_notified(latest_version: str, *, marker_path: Path | None = None) -> bool:
    """True if we have already emailed an update reminder for `latest_version`."""
    p = marker_path or _default_marker_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("notified_version") == latest_version


def record_notified(latest_version: str, *, marker_path: Path | None = None) -> None:
    """Record that an update reminder was emailed for `latest_version`."""
    p = marker_path or _default_marker_path()
    paths.ensure_parent(p)
    p.write_text(json.dumps({"notified_version": latest_version}), encoding="utf-8")
