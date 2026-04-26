"""Data models for the festival organizer pipeline."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MediaFile:
    """All known information about a single media file."""
    source_path: Path

    # Content metadata
    artist: str = ""
    display_artist: str = ""  # Full multi-artist name for filenames/titles
    festival: str = ""
    festival_full: str = ""  # Raw 1001TL festival name before alias resolution
    year: str = ""
    date: str = ""
    set_title: str = ""
    title: str = ""          # For concert films: the concert/show title
    stage: str = ""
    venue: str = ""          # Alias-resolved canonical venue name
    venue_full: str = ""     # Raw 1001TL venue name before alias resolution
    location: str = ""  # Plain-text venue+city from 1001TL h1 tail (fallback when no linked source)
    edition: str = ""
    content_type: str = ""   # "festival_set" | "concert_film" | "unknown"
    artists: list[str] = field(default_factory=list)  # All artists from 1001TL pipe-separated tag
    country: str = ""
    source_type: str = ""          # e.g. "Open Air / Festival", "Event Location"
    metadata_source: str = "" # "1001tracklists" | "metadata" | "filename"
    place: str = ""          # Canonical resolved name used for folder routing
    place_kind: str = ""     # "festival" | "venue" | "location" | "artist"

    # Identifiers
    youtube_id: str = ""
    tracklists_url: str = ""
    tracklists_title: str = ""
    genres: list[str] = field(default_factory=list)
    dj_artwork_url: str = ""

    # Enrichment identifiers
    fanart_url: str = ""
    clearlogo_url: str = ""
    enriched_at: str = ""

    # Technical metadata
    extension: str = ""
    file_type: str = ""      # "video" | "audio"
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    video_format: str = ""
    audio_format: str = ""
    audio_bitrate: str = ""
    overall_bitrate: str = ""
    has_cover: bool = False

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

    @property
    def duration_formatted(self) -> str:
        if self.duration_seconds is not None:
            total = int(self.duration_seconds)
            mins = total // 60
            secs = total % 60
            return f"{mins}m{secs:02d}s"
        return ""


def build_display_title(mf: MediaFile, config=None) -> str:
    """Build a display title for Kodi browse views and MKV TITLE tag.

    Format:
        With stage:    Artist @ Stage, Festival [SetTitle]
        Without stage: Artist @ Festival [SetTitle]
        No festival:   Artist
    """
    if mf.content_type == "festival_set":
        artist = mf.display_artist or mf.artist or "Unknown Artist"
        festival = ""
        if mf.festival:
            if config and mf.edition:
                festival = config.get_place_display(mf.festival, mf.edition)
            else:
                festival = mf.festival
            if mf.set_title:
                festival = f"{festival} {mf.set_title}"
        if mf.stage:
            parts = [f"{artist} @ {mf.stage}"]
            if festival:
                parts.append(festival)
            return ", ".join(parts)
        if festival:
            return f"{artist} @ {festival}"
        return artist
    return mf.title or mf.artist or "Unknown"


@dataclass
class FileAction:
    """A planned move/copy/rename operation."""
    source: Path
    target: Path
    media_file: MediaFile
    action: str = "move"       # "move" | "copy" | "rename"
    status: str = "pending"    # "pending" | "done" | "skipped" | "error"
    error: str = ""
