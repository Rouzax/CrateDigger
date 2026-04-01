"""Parsers for extracting content information from various sources."""
import re
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.normalization import (
    UNICODE_SLASHES,
    extract_youtube_id,
    scene_dots_to_spaces,
    strip_noise_words,
    strip_scene_tags,
)


def _clean_leftover(text: str) -> str:
    """Clean leftover text after year in filename patterns.

    Strips pipe separators (used for stage names in YouTube titles),
    unicode slashes, and orphaned parentheses/brackets.
    """
    text = re.sub(r"[|\uff5c]", " ", text)
    text = UNICODE_SLASHES.sub(" ", text)
    text = re.sub(r"^[)\]]+|[(\[]+$", "", text)
    text = text.strip(" -\u2013\u2014,.()")
    text = re.sub(r"\s+", " ", text).strip()
    return text



def parse_1001tracklists_title(title: str | None, config: Config) -> dict:
    """Parse the 1001TRACKLISTS_TITLE metadata tag.

    Format: "Artist @ Stage, Festival, Location YYYY-MM-DD"

    Returns dict with keys: artist, festival, stage, edition, date, year.
    """
    if not title:
        return {}

    # Decode HTML entities from stored MKV tags (e.g. &amp; -> &)
    import html as html_mod
    title = html_mod.unescape(title)

    result = {}

    if "@" not in title:
        return {}

    artist_part, venue_part = title.split("@", 1)
    result["artist"] = artist_part.strip()

    # Extract date from the end
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*$", venue_part)
    if date_match:
        result["date"] = date_match.group(1)
        result["year"] = date_match.group(1)[:4]
        venue_part = venue_part[:date_match.start()].strip().rstrip(",")

    # Split venue into comma-separated segments
    segments = [s.strip() for s in venue_part.split(",") if s.strip()]

    # Find which segment contains a known festival (check all alias names)
    all_aliases = set(config.festival_aliases.keys()) | config.known_festivals
    festival_idx = None
    for i, seg in enumerate(segments):
        seg_lower = seg.lower()
        for fest in all_aliases:
            if _festival_in_text(fest, seg_lower):
                # Resolve alias and extract location from alias name
                fest, alias_ed = config.resolve_festival_with_edition(seg.strip())
                result["festival"] = fest
                if alias_ed:
                    result["edition"] = alias_ed
                festival_idx = i
                break
        if festival_idx is not None:
            break

    if festival_idx is not None:
        before = segments[:festival_idx]
        after = segments[festival_idx + 1:]

        # Check after-segments for a known edition to separate stage from edition
        known_eds = config.all_known_editions
        loc_offset = None
        for j, seg in enumerate(after):
            for ed in known_eds:
                if ed.lower() in seg.lower():
                    loc_offset = j
                    break
            if loc_offset is not None:
                break

        if before and after and loc_offset is not None:
            # stage = before + after-segments before location
            stage_parts = before + after[:loc_offset]
            result["stage"] = ", ".join(stage_parts) if stage_parts else None
            result.setdefault("edition", ", ".join(after[loc_offset:]))
            if result.get("stage") is None:
                result.pop("stage", None)
        elif before:
            result["stage"] = ", ".join(before)
            if after:
                # Check if any after-segment is a known location
                if loc_offset is not None:
                    stage_after = after[:loc_offset]
                    if stage_after:
                        result["stage"] += ", " + ", ".join(stage_after)
                    result.setdefault("edition", ", ".join(after[loc_offset:]))
                else:
                    result.setdefault("edition", ", ".join(after))
        elif after:
            if loc_offset is not None:
                stage_parts = after[:loc_offset]
                if stage_parts:
                    result["stage"] = ", ".join(stage_parts)
                result.setdefault("edition", ", ".join(after[loc_offset:]))
            else:
                result.setdefault("edition", ", ".join(after))
    elif len(segments) >= 2:
        # No known festival; first segment is venue/festival, rest is edition
        result["festival"] = config.resolve_festival_alias(segments[0])
        result["edition"] = ", ".join(segments[1:])
    elif len(segments) == 1:
        result["festival"] = config.resolve_festival_alias(segments[0])

    return result


def parse_filename(filepath: Path, config: Config) -> dict:
    """Parse artist, festival, year, set title from a filename.

    Handles patterns:
        YYYY - Festival - Artist [WE1]
        ARTIST LIVE @ FESTIVAL YYYY
        ARTIST @ FESTIVAL YYYY
        ARTIST live at FESTIVAL YYYY
        ARTIST at FESTIVAL YYYY
        Artist - Title [YYYY]
        scene.style.name.YYYY.tech.tags
    """
    stem = filepath.stem
    result = {}

    # Extract YouTube ID
    stem, yt_id = extract_youtube_id(stem)
    if yt_id:
        result["youtube_id"] = yt_id

    # Convert scene-style dots to spaces
    stem = scene_dots_to_spaces(stem)

    # Strip scene tags and noise words
    stem = strip_scene_tags(stem)
    stem = strip_noise_words(stem)

    # Clean up
    stem = re.sub(r"\s+", " ", stem).strip(" -\u2013\u2014")

    # Remove "-concert" suffix (Plex convention)
    stem = re.sub(r"-concert\s*$", "", stem, flags=re.IGNORECASE).strip()

    known_festivals = config.known_festivals

    # --- Pattern: YYYY - Part2 - Part3 [WE1/WE2] ---
    m = re.match(r"^(\d{4})\s*[-\u2013]\s*(.+?)\s*[-\u2013]\s*(.+?)(?:(?:\s*[-\u2013]\s*|\s+)(WE\d))?\s*$", stem)
    if m:
        result.setdefault("year", m.group(1))
        part2 = m.group(2).strip()
        part3 = m.group(3).strip()
        weekend = m.group(4)
        # Part2 could be festival or edition; Part3 is artist
        if _is_known_festival(part2, known_festivals):
            result.setdefault("festival", part2)
        else:
            # Could be edition like "Belgium"; store both
            result.setdefault("festival", part2)
            # Check if it's actually an edition for a known parent-dir festival
            for ed in config.all_known_editions:
                if ed.lower() == part2.lower():
                    result["edition"] = part2
                    result.pop("festival", None)
                    break
        result.setdefault("artist", part3)
        if weekend:
            result["set_title"] = weekend
        return result

    # --- Pattern: ARTIST LIVE @ FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s+(?:LIVE|live|Live)\s*@\s*(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = _clean_leftover(m.group(4))
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: ARTIST @ FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s*@\s*(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = _clean_leftover(m.group(4))
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: ARTIST live at FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s+(?:[Ll]ive\s+at)\s+(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = _clean_leftover(m.group(4))
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: ARTIST at FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s+at\s+(.+?)\s+(\d{4})\s*(.*)$", stem)
    if m:
        result.setdefault("artist", m.group(1).strip())
        result.setdefault("festival", m.group(2).strip())
        result.setdefault("year", m.group(3))
        leftover = _clean_leftover(m.group(4))
        if leftover:
            result.setdefault("set_title", leftover)
        return result

    # --- Pattern: Artist - Title [YYYY] ---
    m = re.match(r"^(.+?)\s*[-\u2013\u2014]\s*(.+?)(?:\s+(\d{4}))?\s*$", stem)
    if m:
        part1 = m.group(1).strip()
        part2 = m.group(2).strip()
        year = m.group(3)
        if _is_known_festival(part1, known_festivals):
            result.setdefault("festival", part1)
            result.setdefault("artist", part2)
        elif _is_known_festival(part2, known_festivals):
            result.setdefault("artist", part1)
            result.setdefault("festival", part2)
        else:
            result.setdefault("artist", part1)
            result.setdefault("title", part2)
        if year:
            result.setdefault("year", year)
        return result

    # --- Fallback: extract year, rest is artist ---
    year_match = re.search(r"\b((?:19|20)\d{2})\b", stem)
    if year_match:
        result.setdefault("year", year_match.group(1))
        remainder = (stem[:year_match.start()] + stem[year_match.end():]).strip(" -\u2013\u2014")
        # Check if remainder contains a known festival
        for fest in known_festivals:
            if _festival_in_text(fest, remainder):
                result.setdefault("festival", fest)
                # Remove the festival name to get the artist
                cleaned = re.sub(re.escape(fest), "", remainder, flags=re.IGNORECASE).strip(" -\u2013\u2014")
                if cleaned:
                    result.setdefault("artist", cleaned)
                break
        else:
            if remainder:
                result.setdefault("artist", remainder)
    elif stem:
        result.setdefault("artist", stem)

    return result


def parse_parent_dirs(filepath: Path, root: Path, config: Config) -> dict:
    """Extract metadata from parent directory names relative to root."""
    result = {}

    try:
        relative = filepath.relative_to(root)
    except ValueError:
        return {}

    # Check each directory component (not the filename itself)
    for part in relative.parts[:-1]:
        # Year
        year_match = re.search(r"\b((?:19|20)\d{2})\b", part)
        if year_match:
            result.setdefault("year", year_match.group(1))

        # Known festival
        for fest in config.known_festivals:
            if _festival_in_text(fest, part):
                result.setdefault("festival", fest)
                break

        # Known edition
        for ed in config.all_known_editions:
            if ed.lower() in part.lower():
                result.setdefault("edition", ed)
                break

    return result


def _festival_in_text(fest: str, text: str) -> bool:
    """Check if festival name appears in text as a whole word/phrase."""
    return bool(re.search(r"(?<!\w)" + re.escape(fest) + r"(?!\w)", text, re.IGNORECASE))


def _is_known_festival(name: str, known: set[str]) -> bool:
    """Check if name matches a known festival."""
    return any(_festival_in_text(f, name) for f in known)
