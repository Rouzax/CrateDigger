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
from festival_organizer.mkv_tags import MATROSKA_EXTS, extract_tag_values, write_merged_tags
from festival_organizer.models import MediaFile

logger = logging.getLogger(__name__)


def embed_tags(media_file: MediaFile, target_path: Path) -> bool:
    """Embed metadata tags into an MKV file via mkvpropedit.

    Uses extract-merge-write to preserve existing tags (e.g. 1001TL tags).
    """
    if not metadata.MKVPROPEDIT_PATH:
        return False

    if not target_path.exists() or target_path.suffix.lower() not in MATROSKA_EXTS:
        return False

    tags: dict[str, str] = {}

    if media_file.artist:
        tags["ARTIST"] = media_file.artist

    if media_file.content_type == "festival_set":
        artist = media_file.display_artist or media_file.artist or "Unknown Artist"
        if media_file.stage:
            parts = [f"{artist} @ {media_file.stage}"]
            if media_file.festival:
                festival = media_file.festival
                if media_file.set_title:
                    festival = f"{festival} {media_file.set_title}"
                parts.append(festival)
            title = ", ".join(parts)
        else:
            title = artist
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
        return True  # Nothing to write

    # Skip writing if all tags already match what's in the file
    existing = extract_tag_values(target_path)
    existing_50 = existing.get(50, {})
    existing_70 = existing.get(70, {})

    needs_write = any(
        v != existing_50.get(k, "") for k, v in tags.items()
    ) or any(
        v != existing_70.get(k, "") for k, v in tags_70.items()
    )

    if not needs_write:
        return True  # Already up to date

    # Only stamp ENRICHED_AT when actually writing
    if tags_70:
        tags_70["CRATEDIGGER_ENRICHED_AT"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    all_tags: dict[int, dict[str, str]] = {}
    if tags:
        all_tags[50] = tags
    if tags_70:
        all_tags[70] = tags_70

    return write_merged_tags(target_path, all_tags)


def xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))
