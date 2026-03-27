"""Metadata extraction via MediaInfo CLI and ffprobe fallback."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def find_tool(name: str, fallback_paths: list[str]) -> str | None:
    """Find a CLI tool by name in PATH or at known locations."""
    found = shutil.which(name)
    if found:
        return found
    for path in fallback_paths:
        if os.path.isfile(path):
            return path
    return None


# Locate tools at import time
MEDIAINFO_PATH = find_tool("mediainfo", [
    r"C:\Program Files\MediaInfo\MediaInfo.exe",
    r"C:\Program Files (x86)\MediaInfo\MediaInfo.exe",
    r"C:\Program Files\WinGet\Links\mediainfo.exe",
])

FFPROBE_PATH = find_tool("ffprobe", [
    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
    r"C:\ffmpeg\bin\ffprobe.exe",
    r"C:\Program Files\WinGet\Links\ffprobe.exe",
])


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
    except Exception:
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
    except Exception:
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
