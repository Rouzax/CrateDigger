"""Plex tag embedding via mkvpropedit (opt-in via --embed-tags flag).

Embeds artist, title, and date into MKV file tags so Plex can read them.
Only operates on destination files; never modifies source collection.

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
    CLEAR_TAG,
    MATROSKA_EXTS,
    _tag_values_from_root,
    extract_all_tags,
    has_duplicate_global_blocks,
    write_merged_tags,
)
from festival_organizer.models import MediaFile, build_display_title

logger = logging.getLogger(__name__)


def compute_location_tag(mf: MediaFile) -> str:
    """Pick the rawest available place name for the SYNOPSIS location line.

    Canonical / alias-resolved names (mf.festival, mf.venue, mf.place) live in
    folder paths and posters; the embedded synopsis is a different concept and
    should carry the raw scrape from 1001TL where available. The chain is:

        festival_full  (raw 1001TL festival name)
        venue_full     (raw 1001TL venue name, before alias resolution)
        location       (plain-text h1 tail, e.g. "Alexandra Palace London")

    Returns "" when none of the three are populated.
    """
    return mf.festival_full or mf.venue_full or mf.location


def _build_curated_description(mf: MediaFile) -> str:
    """Build a curated description from MediaFile metadata.

    Format:
        {display_artist} @ {stage}
        {location} ({source_type}), {country}
        Edition: {edition} | {set_title}

    Lines are omitted when data is missing.
    """
    lines: list[str] = []

    # Line 1: artist @ stage
    artist = mf.display_artist or mf.artist or ""
    if artist and mf.stage:
        lines.append(f"{artist} @ {mf.stage}")
    elif artist:
        lines.append(artist)

    # Line 2: location with source type and country
    location = compute_location_tag(mf)
    if location:
        qualifiers: list[str] = []
        if mf.source_type:
            qualifiers.append(f"({mf.source_type})")
        if mf.country:
            qualifiers.append(mf.country)
        if qualifiers:
            lines.append(f"{location} {', '.join(qualifiers)}")
        else:
            lines.append(location)

    # Line 3: edition and/or set title
    edition_parts: list[str] = []
    if mf.edition:
        edition_parts.append(mf.edition)
    if mf.set_title:
        edition_parts.append(mf.set_title)
    if edition_parts:
        lines.append("Edition: " + " | ".join(edition_parts))

    return "\n".join(lines)


def embed_tags(media_file: MediaFile, target_path: Path) -> str:
    """Embed metadata tags into an MKV file via mkvpropedit.

    Uses extract-merge-write to preserve existing tags (e.g. 1001TL tags).
    Returns "done" if tags were written, "skipped" if already up to date,
    or "error" on failure.
    """
    if not metadata.MKVPROPEDIT_PATH:
        logger.debug("embed_tags skipped: mkvpropedit not available")
        return "error"

    if not target_path.exists() or target_path.suffix.lower() not in MATROSKA_EXTS:
        logger.warning(
            "embed_tags skipped: target %s missing or not a Matroska file",
            target_path,
        )
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

    description = _build_curated_description(media_file)
    if description:
        tags["SYNOPSIS"] = description
    tags["DESCRIPTION"] = CLEAR_TAG  # Clear yt-dlp junk

    # Enrichment tags at TTV=70 (collection level)
    tags_70: dict[str, str] = {}
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

    def _cmp(v):
        """Compare value, treating CLEAR_TAG as empty string."""
        return "" if v is CLEAR_TAG else v

    def _render(v):
        """Render a tag value for the DEBUG diff. CLEAR_TAG is a sentinel
        object whose default repr is meaningless in a log line."""
        return "<CLEAR>" if v is CLEAR_TAG else v

    values_differ = any(
        _cmp(v) != existing_50.get(k, "") for k, v in tags.items()
    ) or any(
        _cmp(v) != existing_70.get(k, "") for k, v in tags_70.items()
    )
    needs_heal = root is not None and has_duplicate_global_blocks(root)
    needs_write = values_differ or needs_heal

    if not needs_write:
        return "skipped"  # Already up to date

    diff_50 = {k: (existing_50.get(k, ""), _render(v)) for k, v in tags.items() if _cmp(v) != existing_50.get(k, "")}
    diff_70 = {k: (existing_70.get(k, ""), _render(v)) for k, v in tags_70.items() if _cmp(v) != existing_70.get(k, "")}
    logger.debug("Tag diff for %s: TTV50=%s TTV70=%s", target_path.name, diff_50, diff_70)

    # Only stamp ENRICHED_AT when actually writing
    if tags_70:
        tags_70["CRATEDIGGER_ENRICHED_AT"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    all_tags: dict[int, dict[str, str]] = {}
    if tags:
        all_tags[50] = tags
    if tags_70:
        all_tags[70] = tags_70

    return "done" if write_merged_tags(target_path, all_tags, existing_root=root) else "error"
