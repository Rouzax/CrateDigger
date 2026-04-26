"""Parsers for extracting content information from various sources."""
import logging
import re
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.normalization import (
    UNICODE_SLASHES,
    extract_youtube_id,
    normalize_pipes,
    scene_dots_to_spaces,
    strip_noise_words,
    strip_scene_tags,
)

logger = logging.getLogger(__name__)


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



def parse_filename(filepath: Path, config: Config) -> dict:
    """Parse artist, festival, year, set title from a filename.

    Handles patterns:
        YYYY - Festival - Artist [WE1]
        ARTIST LIVE @ FESTIVAL YYYY
        ARTIST @ FESTIVAL YYYY
        ARTIST live at FESTIVAL YYYY
        ARTIST at FESTIVAL YYYY
        Artist - Title [YYYY]
        Artist WE2 | Festival YYYY (YouTube festival channels)
        scene.style.name.YYYY.tech.tags
    """
    stem = filepath.stem
    result = {}

    # Extract YouTube ID
    stem, yt_id = extract_youtube_id(stem)
    if yt_id:
        result["youtube_id"] = yt_id

    # Normalize fullwidth pipe to regular pipe (YouTube title artifact)
    stem = normalize_pipes(stem)

    # Convert scene-style dots to spaces
    stem = scene_dots_to_spaces(stem)

    # Strip scene tags and noise words
    stem = strip_scene_tags(stem)
    stem = strip_noise_words(stem)

    # Clean up
    stem = re.sub(r"\s+", " ", stem).strip(" -\u2013\u2014")

    # Remove "-concert" suffix (Plex convention)
    stem = re.sub(r"-concert\s*$", "", stem, flags=re.IGNORECASE).strip()

    known_festivals = config.known_places

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

    # --- Pattern: ARTIST [- ] [live] at FESTIVAL YYYY ---
    m = re.match(r"^(.+?)\s*[-\u2013\u2014]?\s+(?:[Ll]ive\s+)?[Aa]t\s+(.+?)\s+(\d{4})\s*(.*)$", stem)
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

    # --- Pattern: Artist [WE2] | Festival YYYY (YouTube festival channels) ---
    m = re.match(r"^(.+?)\s+(WE\d)\s*\|\s*(.+?)\s+(\d{4})\s*$", stem)
    if not m:
        m = re.match(r"^(.+?)\s*\|\s*(.+?)\s+(\d{4})\s*$", stem)
    if m:
        groups = m.groups()
        if len(groups) == 4:
            artist, weekend, festival_part, year = groups
            result.setdefault("artist", artist.strip())
            result.setdefault("set_title", weekend)
            result.setdefault("year", year)
            if _is_known_festival(festival_part.strip(), known_festivals):
                result.setdefault("festival", festival_part.strip())
            else:
                result.setdefault("festival", festival_part.strip())
        else:
            artist, festival_part, year = groups
            result.setdefault("artist", artist.strip())
            result.setdefault("year", year)
            if _is_known_festival(festival_part.strip(), known_festivals):
                result.setdefault("festival", festival_part.strip())
            else:
                result.setdefault("festival", festival_part.strip())
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
                cleaned = _clean_leftover(cleaned)
                if cleaned:
                    result.setdefault("artist", cleaned)
                break
        else:
            if remainder:
                result.setdefault("artist", _clean_leftover(remainder))
    elif stem:
        result.setdefault("artist", stem)

    logger.debug("parse_filename fallback for %r: %s", stem, result)
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
        for fest in config.known_places:
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
