"""Data models for the festival organizer pipeline."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MediaFile:
    """All known information about a single media file."""
    source_path: Path

    # Content metadata
    artist: str = ""
    festival: str = ""
    year: str = ""
    date: str = ""
    set_title: str = ""
    title: str = ""          # For concert films: the concert/show title
    stage: str = ""
    location: str = ""
    content_type: str = ""   # "festival_set" | "concert_film" | "unknown"
    metadata_source: str = "" # "1001tracklists" | "metadata" | "filename"

    # Identifiers
    youtube_id: str = ""
    tracklists_url: str = ""
    tracklists_title: str = ""
    genres: list[str] = field(default_factory=list)
    event_artwork_url: str = ""

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


@dataclass
class FileAction:
    """A planned move/copy/rename operation."""
    source: Path
    target: Path
    media_file: MediaFile
    action: str = "move"       # "move" | "copy" | "rename"
    status: str = "pending"    # "pending" | "done" | "skipped" | "error"
    error: str = ""
