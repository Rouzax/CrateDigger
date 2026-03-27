"""Template engine for folder paths and filenames."""
import re
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import MediaFile
from festival_organizer.normalization import safe_filename


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

    Returns a filename string like "2024 - AMF - Martin Garrix.mkv".
    """
    ct = media_file.content_type
    ext = media_file.extension

    # For unknown content or when we have too little info, keep original name
    if ct == "unknown" or ct == "":
        return media_file.source_path.name

    template = config.get_filename_template(ct)
    values = _build_values(media_file, config)

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

    # Append set_title if present (not in template but we add it)
    if media_file.set_title and media_file.set_title not in rendered:
        rendered = f"{rendered} - {safe_filename(media_file.set_title)}"

    return rendered + ext


def _build_values(media_file: MediaFile, config: Config) -> dict[str, str]:
    """Build the substitution values dict for a media file."""
    # Resolve festival display name (with location if configured)
    festival = media_file.festival
    if festival:
        festival = config.get_festival_display(festival, media_file.location)

    return {
        "artist": safe_filename(media_file.artist),
        "festival": safe_filename(festival),
        "year": media_file.year,
        "date": media_file.date,
        "location": safe_filename(media_file.location),
        "stage": safe_filename(media_file.stage),
        "set_title": safe_filename(media_file.set_title),
        "title": safe_filename(media_file.title or media_file.set_title),
    }


def _render(template: str, values: dict[str, str], fallbacks: dict[str, str]) -> str:
    """Substitute {placeholders} in a template string.

    Empty values are replaced with fallback values from config.
    Path separators in the template are preserved.
    """
    result = template
    for key, value in values.items():
        placeholder = "{" + key + "}"
        if placeholder in result:
            if value:
                result = result.replace(placeholder, value)
            else:
                # Use fallback
                fallback_key = f"unknown_{key}"
                fallback = fallbacks.get(fallback_key, "")
                if fallback:
                    result = result.replace(placeholder, fallback)
                else:
                    result = result.replace(placeholder, "Unknown")

    # Clean up double separators from empty values
    result = re.sub(r"/ +/", "/", result)
    result = re.sub(r" +- +- +", " - ", result)
    result = result.strip("/ -")

    return result
