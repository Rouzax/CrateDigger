"""Recursive media file scanner with skip-pattern filtering."""
import logging
from pathlib import Path

from festival_organizer.config import Config

logger = logging.getLogger(__name__)


def scan_folder(root: Path, config: Config) -> list[Path]:
    """Recursively find all media files under root, respecting skip patterns.

    Returns sorted list of Path objects.
    """
    media_exts = config.media_extensions
    files = []

    try:
        entries = sorted(root.rglob("*"))
    except OSError as e:
        logger.warning("Could not scan %s: %s", root, e)
        return files

    for item in entries:
        try:
            if not item.is_file():
                continue
        except OSError:
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
