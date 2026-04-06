"""Template engine for folder paths and filenames.

Supports Sonarr-style collapsing tokens: literal characters inside braces
collapse with the field when empty.  ``{field}`` is a required field (uses
fallback when empty), while ``{[stage]}`` or ``{ - set_title}`` are optional
decorated fields that vanish entirely when the field is empty.
"""
import re

from festival_organizer.config import Config
from festival_organizer.models import MediaFile
from festival_organizer.normalization import safe_filename

# All known placeholder field names used in templates.
_KNOWN_FIELDS = frozenset({
    "artist", "festival", "year", "date",
    "edition", "stage", "set_title", "title",
})

# Regex that matches a single ``{...}`` token (non-greedy).
_TOKEN_RE = re.compile(r"\{([^}]+)\}")


def render_folder(media_file: MediaFile, config: Config, layout_name: str | None = None) -> str:
    """Render the folder path for a media file using the configured layout template.

    Returns a relative path string like "Artist/Festival/2024".
    """
    ct = media_file.content_type

    # Unknown content goes to _Needs Review
    if ct == "unknown" or ct == "":
        return "_Needs Review"

    template = config.get_layout_template(ct, layout_name)
    values = _build_values(media_file, config)
    return _render(template, values, config.fallback_values)


def render_filename(media_file: MediaFile, config: Config) -> str:
    """Render the filename for a media file using the configured template.

    Returns a filename string like "2024 - Martin Garrix - AMF.mkv".
    """
    ct = media_file.content_type
    ext = media_file.extension

    # For unknown content or when we have too little info, keep original name
    if ct == "unknown" or ct == "":
        return media_file.source_path.name

    template = config.get_filename_template(ct)
    values = _build_values(media_file, config, for_filename=True)

    rendered = _render(template, values, config.fallback_values)

    # If the rendered name is mostly fallback values, keep the original
    fallbacks_used = sum(
        1 for v in config.fallback_values.values()
        if v in rendered
    )
    if fallbacks_used >= 2:
        return media_file.source_path.name

    # Clean up and append extension
    rendered = safe_filename(rendered)
    if not rendered:
        return media_file.source_path.name

    return rendered + ext


def _build_values(media_file: MediaFile, config: Config, *, for_filename: bool = False) -> dict[str, str]:
    """Build the substitution values dict for a media file."""
    festival = media_file.festival

    # Validate edition: only include if it matches a configured edition
    edition = ""
    if festival and media_file.edition:
        fc = config.festival_config.get(festival, {})
        known = [e.lower() for e in fc.get("editions", [])]
        if media_file.edition.lower() in known:
            edition = media_file.edition

    # For filenames, use display_artist (full B2B name); for folders, use artist (primary)
    artist = media_file.artist
    if for_filename and media_file.display_artist:
        artist = media_file.display_artist

    # For folder paths, fall back to artist when festival is empty.
    # Standalone sets (no festival) should be grouped under the artist folder
    # rather than a fallback like "_Needs Review".
    folder_festival = festival
    if not for_filename and not festival and artist:
        folder_festival = artist

    return {
        "artist": safe_filename(artist),
        "festival": safe_filename(folder_festival),
        "year": media_file.year,
        "date": media_file.date,
        "edition": safe_filename(edition),
        "stage": safe_filename(media_file.stage),
        "set_title": safe_filename(media_file.set_title),
        "title": safe_filename(media_file.title or media_file.set_title),
    }


# Fields sorted longest-first so "set_title" matches before "title".
_FIELDS_BY_LENGTH = sorted(_KNOWN_FIELDS, key=len, reverse=True)


def _parse_token(content: str) -> tuple[str, str, str]:
    """Split the content inside ``{...}`` into (prefix, field_name, suffix).

    The field name is identified by matching against ``_KNOWN_FIELDS``.
    Everything before the field name is prefix; everything after is suffix.
    If no known field is found, the entire content is treated as the field name
    with empty prefix/suffix (for forward-compatibility).
    """
    for field in _FIELDS_BY_LENGTH:
        idx = content.find(field)
        if idx != -1:
            prefix = content[:idx]
            suffix = content[idx + len(field):]
            return prefix, field, suffix
    return "", content, ""


def _render(template: str, values: dict[str, str], fallbacks: dict[str, str]) -> str:
    """Substitute ``{...}`` tokens in a template string.

    Supports two token types:
    - ``{field}``  required field; uses fallback when empty.
    - ``{literal field literal}``  optional decorated field; the entire token
      (and any adjacent whitespace) collapses when the field is empty.
    """
    parts: list[str] = []
    last_end = 0

    for m in _TOKEN_RE.finditer(template):
        # Text between the previous token and this one
        parts.append(template[last_end:m.start()])
        last_end = m.end()

        content = m.group(1)
        prefix, field, suffix = _parse_token(content)
        value = values.get(field, "")
        has_decorators = bool(prefix or suffix)

        if value:
            parts.append(f"{prefix}{value}{suffix}")
        elif has_decorators:
            # Optional decorated token with empty value: collapse entirely.
            # Also strip trailing whitespace from the previous literal part
            # so we don't get double spaces.
            if parts and parts[-1].endswith(" "):
                parts[-1] = parts[-1].rstrip(" ")
        else:
            # Required field with empty value: use fallback
            fallback_key = f"unknown_{field}"
            fallback = fallbacks.get(fallback_key, "")
            parts.append(fallback if fallback else "Unknown")

        last_end = m.end()

    # Trailing literal text after the last token
    parts.append(template[last_end:])

    result = "".join(parts)

    # Safety-net cleanup for edge cases
    result = re.sub(r"/+", "/", result)
    result = re.sub(r" +- +- +", " - ", result)
    result = result.strip("/ -")

    return result
