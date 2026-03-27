"""Library root detection and marker management."""
import json
from pathlib import Path

MARKER_DIR = ".cratedigger"


def find_library_root(start_path: Path) -> Path | None:
    """Walk up from start_path looking for .cratedigger/ marker.

    Returns the directory containing the marker, or None if not found.
    Stops at filesystem root to avoid infinite loops.
    """
    current = start_path.resolve()
    while True:
        if (current / MARKER_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def init_library(root: Path, layout: str | None = None) -> Path:
    """Initialize a library at root by creating .cratedigger/ marker.

    If .cratedigger/config.json already exists, merges layout setting
    without overwriting existing user settings.

    Returns path to the .cratedigger/ directory.
    """
    marker = root / MARKER_DIR
    marker.mkdir(exist_ok=True)

    config_path = marker / "config.json"
    if config_path.exists():
        existing = json.loads(config_path.read_text(encoding="utf-8"))
        if layout and "default_layout" not in existing:
            existing["default_layout"] = layout
            config_path.write_text(
                json.dumps(existing, indent=2) + "\n", encoding="utf-8"
            )
    else:
        config = {}
        if layout:
            config["default_layout"] = layout
        config_path.write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

    return marker
