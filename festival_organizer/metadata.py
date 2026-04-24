"""Metadata extraction via MediaInfo CLI and ffprobe fallback.

Logging:
    Logger: 'festival_organizer.metadata'
    Key events:
        - mediainfo.fail (DEBUG): mediainfo CLI call failed
        - ffprobe.fail (DEBUG): ffprobe CLI call failed
    See docs/logging.md for full guidelines.
"""
import json
import logging
import platform
import re
import shutil
import subprocess
from pathlib import Path

from festival_organizer.normalization import fix_mojibake
from festival_organizer.subprocess_utils import tracked_run

logger = logging.getLogger(__name__)


def _fix_string_values(d: dict) -> dict:
    """Apply fix_mojibake to every string value in a metadata dict (in place)."""
    for k, v in d.items():
        if isinstance(v, str):
            d[k] = fix_mojibake(v)
    return d


# Package → tool names for install hints
_INSTALL_PACKAGES = {
    "mediainfo": {"brew": "mediainfo", "apt": "mediainfo", "winget": "MediaArea.MediaInfo.CLI"},
    "ffprobe": {"brew": "ffmpeg", "apt": "ffmpeg", "winget": "Gyan.FFmpeg"},
    "mkvextract": {"brew": "mkvtoolnix", "apt": "mkvtoolnix", "winget": "MKVToolNix.MKVToolNix"},
    "mkvpropedit": {"brew": "mkvtoolnix", "apt": "mkvtoolnix", "winget": "MKVToolNix.MKVToolNix"},
    "mkvmerge": {"brew": "mkvtoolnix", "apt": "mkvtoolnix", "winget": "MKVToolNix.MKVToolNix"},
}


def find_tool(name: str, fallback_paths: list[str] | None = None, configured_path: str | None = None) -> str | None:
    """Find an external tool by name.

    Priority:
    1. configured_path (from user config) — if file exists
    2. System PATH via shutil.which
    3. fallback_paths (legacy, for backward compatibility)

    Returns the resolved path string, or None if not found.
    """
    if configured_path and Path(configured_path).is_file():
        return configured_path

    found = shutil.which(name)
    if found:
        return found

    # Legacy fallback paths support
    if fallback_paths:
        for path in fallback_paths:
            if Path(path).is_file():
                return path

    return None


def get_install_hint(tool_name: str) -> str:
    """Return a platform-specific install command hint."""
    system = platform.system()
    pkg = _INSTALL_PACKAGES.get(tool_name, {})

    if system == "Darwin":
        return f"Install with: brew install {pkg.get('brew', tool_name)}"
    elif system == "Linux":
        return f"Install with: apt install {pkg.get('apt', tool_name)}"
    else:
        return f"Install with: winget install {pkg.get('winget', tool_name)}"


# Resolved at import time (no config); reconfigured via configure_tools()
MEDIAINFO_PATH = find_tool("mediainfo")
FFPROBE_PATH = find_tool("ffprobe")
MKVEXTRACT_PATH = find_tool("mkvextract")
MKVPROPEDIT_PATH = find_tool("mkvpropedit")
MKVMERGE_PATH = find_tool("mkvmerge")


def configure_tools(config: object) -> None:
    """Re-resolve tool paths using config-provided overrides."""
    global MEDIAINFO_PATH, FFPROBE_PATH, MKVEXTRACT_PATH, MKVPROPEDIT_PATH, MKVMERGE_PATH
    tool_paths = config.tool_paths if hasattr(config, "tool_paths") else {}
    MEDIAINFO_PATH = find_tool("mediainfo", configured_path=tool_paths.get("mediainfo"))
    FFPROBE_PATH = find_tool("ffprobe", configured_path=tool_paths.get("ffprobe"))
    MKVEXTRACT_PATH = find_tool("mkvextract", configured_path=tool_paths.get("mkvextract"))
    MKVPROPEDIT_PATH = find_tool("mkvpropedit", configured_path=tool_paths.get("mkvpropedit"))
    MKVMERGE_PATH = find_tool("mkvmerge", configured_path=tool_paths.get("mkvmerge"))


def _first_tag(*sources: dict, keys: list[str]) -> str:
    """Return the first non-empty value found across sources for the given keys."""
    for key in keys:
        for src in sources:
            val = src.get(key, "")
            if val:
                return val
    return ""


# Tag key lookup: maps output field to (new_name, old_name) pairs.
# MediaInfo stores custom tags in both the general track and an "extra" sub-dict.
# Old "1001TRACKLISTS_*" names are kept for backward compatibility with files
# tagged before the CRATEDIGGER_ prefix was adopted.  The extra dict prefixes
# old names with an underscore.
_1001TL_TAG_KEYS: dict[str, list[str]] = {
    "tracklists_title": ["CRATEDIGGER_1001TL_TITLE", "1001TRACKLISTS_TITLE", "_1001TRACKLISTS_TITLE"],
    "tracklists_url": ["CRATEDIGGER_1001TL_URL", "1001TRACKLISTS_URL", "_1001TRACKLISTS_URL"],
    "tracklists_id": ["CRATEDIGGER_1001TL_ID", "1001TRACKLISTS_ID", "_1001TRACKLISTS_ID"],
    "tracklists_date": ["CRATEDIGGER_1001TL_DATE", "1001TRACKLISTS_DATE", "_1001TRACKLISTS_DATE"],
    "tracklists_genres": ["CRATEDIGGER_1001TL_GENRES", "1001TRACKLISTS_GENRES", "_1001TRACKLISTS_GENRES"],
    "tracklists_dj_artwork": ["CRATEDIGGER_1001TL_DJ_ARTWORK", "1001TRACKLISTS_DJ_ARTWORK", "_1001TRACKLISTS_DJ_ARTWORK"],
    "tracklists_stage": ["CRATEDIGGER_1001TL_STAGE"],
    "tracklists_venue": ["CRATEDIGGER_1001TL_VENUE"],
    "tracklists_location": ["CRATEDIGGER_1001TL_LOCATION"],
    "tracklists_festival": ["CRATEDIGGER_1001TL_FESTIVAL"],
    "tracklists_artists": ["CRATEDIGGER_1001TL_ARTISTS"],
    "tracklists_country": ["CRATEDIGGER_1001TL_COUNTRY"],
    "tracklists_source_type": ["CRATEDIGGER_1001TL_SOURCE_TYPE"],
}

_ENRICHMENT_TAG_KEYS: dict[str, str] = {
    "fanart_url": "CRATEDIGGER_FANART_URL",
    "clearlogo_url": "CRATEDIGGER_CLEARLOGO_URL",
    "enriched_at": "CRATEDIGGER_ENRICHED_AT",
}


def parse_mediainfo_json(data: dict) -> dict:
    """Parse MediaInfo JSON output into a flat metadata dict."""
    tracks = data.get("media", {}).get("track", [])
    if not tracks:
        return {}

    general = tracks[0]
    video = next((t for t in tracks if t.get("@type") == "Video"), {})
    audio = next((t for t in tracks if t.get("@type") == "Audio"), {})
    extra = general.get("extra", {})

    result = {
        "title": general.get("Title", ""),
        "duration_seconds": _parse_duration(general.get("Duration", "")),
        "overall_bitrate": general.get("OverallBitRate", ""),
        "format": general.get("Format", ""),
        "encoded_date": general.get("Encoded_Date", ""),
        # yt-dlp / custom tags
        "artist_tag": general.get("ARTIST", "") or extra.get("ARTIST", ""),
        "date_tag": general.get("DATE", "") or extra.get("DATE", ""),
        "description": general.get("Description", ""),
        "comment": general.get("Comment", ""),
        "purl": general.get("PURL", "") or extra.get("PURL", ""),
        # Video
        "video_format": video.get("Format", ""),
        "width": _int_or_none(video.get("Width", "")),
        "height": _int_or_none(video.get("Height", "")),
        "video_bitrate": video.get("BitRate", ""),
        "framerate": video.get("FrameRate", ""),
        # Audio
        "audio_format": audio.get("Format", ""),
        "audio_bitrate": audio.get("BitRate", ""),
        "audio_channels": audio.get("Channels", ""),
        "audio_sampling_rate": audio.get("SamplingRate", ""),
        # Cover art
        "has_cover": bool(general.get("Attachments", "")),
    }

    # 1001Tracklists tags (new name first, fall back to old; check extra for both)
    for field, tag_keys in _1001TL_TAG_KEYS.items():
        result[field] = _first_tag(general, extra, keys=tag_keys)

    # Enrichment tags
    for field, tag_key in _ENRICHMENT_TAG_KEYS.items():
        result[field] = general.get(tag_key, "") or extra.get(tag_key, "")

    return _fix_string_values(result)


def _extract_mediainfo(filepath: Path) -> dict:
    """Run MediaInfo CLI and return parsed metadata."""
    if not MEDIAINFO_PATH:
        return {}
    try:
        result = tracked_run(
            [MEDIAINFO_PATH, "--Output=JSON", str(filepath)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        return parse_mediainfo_json(data)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("mediainfo failed for %s: %s", filepath, e)
        return {}


def _extract_ffprobe(filepath: Path) -> dict:
    """Run ffprobe as fallback and return parsed metadata."""
    if not FFPROBE_PATH:
        return {}
    try:
        result = tracked_run(
            [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(filepath)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        tags = fmt.get("tags", {})
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})

        result_dict: dict = {
            "title": tags.get("title", "") or tags.get("TITLE", ""),
            "duration_seconds": _parse_duration(fmt.get("duration", "")),
            "overall_bitrate": fmt.get("bit_rate", ""),
            "format": fmt.get("format_long_name", ""),
            "artist_tag": tags.get("artist", "") or tags.get("ARTIST", ""),
            "date_tag": tags.get("date", "") or tags.get("DATE", ""),
            "description": tags.get("description", "") or tags.get("DESCRIPTION", ""),
            "comment": tags.get("comment", "") or tags.get("COMMENT", ""),
            "purl": tags.get("purl", "") or tags.get("PURL", ""),
            "video_format": video.get("codec_name", ""),
            "width": _int_or_none(video.get("width", "")),
            "height": _int_or_none(video.get("height", "")),
            "video_bitrate": video.get("bit_rate", ""),
            "framerate": video.get("r_frame_rate", ""),
            "audio_format": audio.get("codec_name", ""),
            "audio_bitrate": audio.get("bit_rate", ""),
            "audio_channels": audio.get("channels", ""),
            "audio_sampling_rate": audio.get("sample_rate", ""),
            "has_cover": False,  # ffprobe doesn't easily report attachments
        }

        # 1001Tracklists tags (ffprobe uses flat tag namespace)
        for field, tag_keys in _1001TL_TAG_KEYS.items():
            result_dict[field] = _first_tag(tags, keys=tag_keys)

        # Enrichment tags
        for field, tag_key in _ENRICHMENT_TAG_KEYS.items():
            result_dict[field] = tags.get(tag_key, "")

        return _fix_string_values(result_dict)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("ffprobe failed for %s: %s", filepath, e)
        return {}


def extract_metadata(filepath: Path) -> dict:
    """Extract metadata from a file. Tries MediaInfo first, ffprobe fallback."""
    meta = _extract_mediainfo(filepath)
    if not meta:
        meta = _extract_ffprobe(filepath)
    return meta


def _parse_duration(value: str | float | None) -> float | None:
    """Parse a duration value to seconds."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    m = re.match(r"(\d+):(\d+):(\d+)", str(value))
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return None


def _int_or_none(value: str | int | None) -> int | None:
    """Parse an integer, handling MediaInfo's space-formatted numbers."""
    if not value:
        return None
    try:
        return int(str(value).replace(" ", "").replace("\u202f", ""))
    except (ValueError, TypeError):
        return None
