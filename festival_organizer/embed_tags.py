"""Plex tag embedding via mkvpropedit (opt-in via --embed-tags flag).

Embeds artist, title, and date into MKV file tags so Plex can read them.
Only operates on destination files — never modifies source collection.

Logging:
    Logger: 'festival_organizer.embed_tags'
    Key events:
        - tags.embed_error (DEBUG): Tag embedding via mkvpropedit failed
    See docs/logging.md for full guidelines.
"""
import logging
from pathlib import Path

from festival_organizer import metadata
from festival_organizer.mkv_tags import write_merged_tags
from festival_organizer.models import MediaFile

logger = logging.getLogger(__name__)


def embed_tags(media_file: MediaFile, target_path: Path) -> bool:
    """Embed metadata tags into an MKV file via mkvpropedit.

    Uses extract-merge-write to preserve existing tags (e.g. 1001TL tags).
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not target_path.exists() or target_path.suffix.lower() != ".mkv":
        return False

    tags: dict[str, str] = {}

    if media_file.artist:
        tags["ARTIST"] = media_file.artist

    title = media_file.title or media_file.set_title or ""
    if media_file.festival:
        title = f"{media_file.festival} {media_file.year}".strip()
    if title:
        tags["TITLE"] = title

    date = media_file.date or media_file.year
    if date:
        tags["DATE_RELEASED"] = date

    if not tags:
        return True  # Nothing to write

    return write_merged_tags(target_path, {50: tags})


def xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))
