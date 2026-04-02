"""Search query building from filenames and MediaFile objects."""
import re
from pathlib import Path

from festival_organizer.normalization import extract_youtube_id, strip_scene_tags, strip_noise_words, UNICODE_SLASHES


def build_search_query(source_path: Path) -> str:
    """Build a search query string from a media file path.

    Strips extension, YouTube ID, scene tags, noise words, and converts separators to spaces.
    """
    stem = source_path.stem

    # Strip YouTube ID
    stem, _ = extract_youtube_id(stem)

    # Normalize unicode slashes (KI⧸KI → KI KI)
    stem = UNICODE_SLASHES.sub(" ", stem)

    # Convert common separators to spaces
    stem = re.sub(r"[-_.]", " ", stem)

    # Strip scene tags and noise words
    stem = strip_scene_tags(stem)
    stem = strip_noise_words(stem)

    # Remove empty parentheses/brackets left after stripping
    stem = re.sub(r"[(\[]\s*[)\]]", "", stem)

    # Collapse whitespace
    stem = re.sub(r"\s+", " ", stem).strip()

    return stem


def expand_aliases_in_query(query: str, aliases: dict[str, str]) -> str:
    """Expand known abbreviations in a query string to their full names.

    Args:
        query: search query string
        aliases: lowercase-keyed alias map (e.g. {"amf": "Amsterdam Music Festival"})

    Returns:
        Query with abbreviations replaced by full names.
    """
    for abbrev, full_name in aliases.items():
        query = re.sub(rf"\b{re.escape(abbrev)}\b", full_name, query, flags=re.IGNORECASE)
    return query


def detect_tracklist_source(input_str: str) -> dict:
    """Classify input as URL, ID, or search query.

    Returns {"type": "url"|"id"|"search", "value": str}
    """
    input_str = input_str.strip()

    # URL: contains 1001tracklists.com
    if "1001tracklists.com" in input_str.lower():
        return {"type": "url", "value": input_str}

    # ID: short alphanumeric string (6-12 chars, lowercase + digits)
    if re.match(r"^[a-z0-9]{6,12}$", input_str):
        return {"type": "id", "value": input_str}

    # Everything else is a search query
    return {"type": "search", "value": input_str}


def extract_tracklist_id(url: str) -> str:
    """Extract tracklist ID from a 1001tracklists URL.

    Example: "https://www.1001tracklists.com/tracklist/1g6g22ut/..." -> "1g6g22ut"

    Raises ValueError if no ID found.
    """
    match = re.search(r"/tracklist/([a-z0-9]+)/", url)
    if match:
        return match.group(1)
    # Try without trailing slash
    match = re.search(r"/tracklist/([a-z0-9]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract tracklist ID from URL: {url}")
