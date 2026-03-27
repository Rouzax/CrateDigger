"""Recursive media file scanner with skip-pattern filtering."""
from pathlib import Path

from festival_organizer.config import Config


def scan_folder(root: Path, config: Config) -> list[Path]:
    """Recursively find all media files under root, respecting skip patterns.

    Returns sorted list of Path objects.
    """
    media_exts = config.media_extensions
    files = []

    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        if item.suffix.lower() not in media_exts:
            continue

        # Check skip patterns against relative path
        try:
            rel = str(item.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = item.name

        if config.should_skip(rel):
            continue

        files.append(item)

    return files
