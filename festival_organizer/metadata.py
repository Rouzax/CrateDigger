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

logger = logging.getLogger(__name__)


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


def configure_tools(config) -> None:
    """Re-resolve tool paths using config-provided overrides."""
    global MEDIAINFO_PATH, FFPROBE_PATH, MKVEXTRACT_PATH, MKVPROPEDIT_PATH, MKVMERGE_PATH
    tool_paths = config.tool_paths if hasattr(config, "tool_paths") else {}
    MEDIAINFO_PATH = find_tool("mediainfo", configured_path=tool_paths.get("mediainfo"))
    FFPROBE_PATH = find_tool("ffprobe", configured_path=tool_paths.get("ffprobe"))
    MKVEXTRACT_PATH = find_tool("mkvextract", configured_path=tool_paths.get("mkvextract"))
    MKVPROPEDIT_PATH = find_tool("mkvpropedit", configured_path=tool_paths.get("mkvpropedit"))
    MKVMERGE_PATH = find_tool("mkvmerge", configured_path=tool_paths.get("mkvmerge"))


def parse_mediainfo_json(data: dict) -> dict:
    """Parse MediaInfo JSON output into a flat metadata dict."""
    tracks = data.get("media", {}).get("track", [])
    if not tracks:
        return {}

    general = tracks[0]
    video = next((t for t in tracks if t.get("@type") == "Video"), {})
    audio = next((t for t in tracks if t.get("@type") == "Audio"), {})
    extra = general.get("extra", {})

    return {
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
        # 1001Tracklists
        "tracklists_title": (
            general.get("1001TRACKLISTS_TITLE", "")
            or extra.get("_1001TRACKLISTS_TITLE", "")
        ),
        "tracklists_url": (
            general.get("1001TRACKLISTS_URL", "")
            or extra.get("_1001TRACKLISTS_URL", "")
        ),
        "tracklists_id": (
            general.get("1001TRACKLISTS_ID", "")
            or extra.get("_1001TRACKLISTS_ID", "")
        ),
        "tracklists_date": (
            general.get("1001TRACKLISTS_DATE", "")
            or extra.get("_1001TRACKLISTS_DATE", "")
        ),
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


def _extract_mediainfo(filepath: Path) -> dict:
    """Run MediaInfo CLI and return parsed metadata."""
    if not MEDIAINFO_PATH:
        return {}
    try:
        result = subprocess.run(
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
        result = subprocess.run(
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
        return {
            "title": tags.get("title", "") or tags.get("TITLE", ""),
            "duration_seconds": _parse_duration(fmt.get("duration", "")),
            "overall_bitrate": fmt.get("bit_rate", ""),
            "format": fmt.get("format_long_name", ""),
            "artist_tag": tags.get("artist", "") or tags.get("ARTIST", ""),
            "date_tag": tags.get("date", "") or tags.get("DATE", ""),
            "description": tags.get("description", "") or tags.get("DESCRIPTION", ""),
            "comment": tags.get("comment", "") or tags.get("COMMENT", ""),
            "purl": tags.get("purl", "") or tags.get("PURL", ""),
            "tracklists_title": tags.get("1001TRACKLISTS_TITLE", ""),
            "tracklists_url": tags.get("1001TRACKLISTS_URL", ""),
            "tracklists_id": tags.get("1001TRACKLISTS_ID", ""),
            "tracklists_date": tags.get("1001TRACKLISTS_DATE", ""),
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
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.debug("ffprobe failed for %s: %s", filepath, e)
        return {}


def extract_metadata(filepath: Path) -> dict:
    """Extract metadata from a file. Tries MediaInfo first, ffprobe fallback."""
    meta = _extract_mediainfo(filepath)
    if not meta:
        meta = _extract_ffprobe(filepath)
    return meta


def _parse_duration(value) -> float | None:
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


def _int_or_none(value) -> int | None:
    """Parse an integer, handling MediaInfo's space-formatted numbers."""
    if not value:
        return None
    try:
        return int(str(value).replace(" ", "").replace("\u202f", ""))
    except (ValueError, TypeError):
        return None
