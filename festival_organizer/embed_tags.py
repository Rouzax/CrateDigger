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
from datetime import datetime, timezone
from pathlib import Path

from festival_organizer import metadata
from festival_organizer.mkv_tags import (
    MATROSKA_EXTS,
    _tag_values_from_root,
    extract_all_tags,
    write_merged_tags,
)
from festival_organizer.models import MediaFile, build_display_title

logger = logging.getLogger(__name__)


def embed_tags(media_file: MediaFile, target_path: Path) -> str:
    """Embed metadata tags into an MKV file via mkvpropedit.

    Uses extract-merge-write to preserve existing tags (e.g. 1001TL tags).
    Returns "done" if tags were written, "skipped" if already up to date,
    or "error" on failure.
    """
    if not metadata.MKVPROPEDIT_PATH:
        return "error"

    if not target_path.exists() or target_path.suffix.lower() not in MATROSKA_EXTS:
        return "error"

    tags: dict[str, str] = {}

    if media_file.artist:
        tags["ARTIST"] = media_file.artist

    if media_file.content_type == "festival_set":
        title = build_display_title(media_file)
    else:
        title = media_file.title or media_file.set_title or ""
    if title:
        tags["TITLE"] = title

    date = media_file.date or media_file.year
    if date:
        tags["DATE_RELEASED"] = date

    # Enrichment tags at TTV=70 (collection level)
    tags_70: dict[str, str] = {}
    if media_file.mbid:
        tags_70["CRATEDIGGER_MBID"] = media_file.mbid
    if media_file.fanart_url:
        tags_70["CRATEDIGGER_FANART_URL"] = media_file.fanart_url
    if media_file.clearlogo_url:
        tags_70["CRATEDIGGER_CLEARLOGO_URL"] = media_file.clearlogo_url

    if not tags and not tags_70:
        return "skipped"  # Nothing to write

    # Extract tags once; reuse for comparison and write
    root = extract_all_tags(target_path)
    existing = _tag_values_from_root(root) if root is not None else {}
    existing_50 = existing.get(50, {})
    existing_70 = existing.get(70, {})

    needs_write = any(
        v != existing_50.get(k, "") for k, v in tags.items()
    ) or any(
        v != existing_70.get(k, "") for k, v in tags_70.items()
    )

    if not needs_write:
        return "skipped"  # Already up to date

    # Only stamp ENRICHED_AT when actually writing
    if tags_70:
        tags_70["CRATEDIGGER_ENRICHED_AT"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    all_tags: dict[int, dict[str, str]] = {}
    if tags:
        all_tags[50] = tags
    if tags_70:
        all_tags[70] = tags_70

    return "done" if write_merged_tags(target_path, all_tags, existing_root=root) else "error"


def xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))
