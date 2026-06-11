"""Data models for the run-summary email feature."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EmailSet:
    """One set/album row in an email."""
    artist: str
    event: str            # festival/place name; "" for concerts/albums
    year: str
    note: str             # stage or bracket detail, may be ""
    genres: list[str]
    metric: str           # e.g. "19 tracks · 1h 30m" or "22 chapters"
    poster_path: Path | None
    kind: str             # "festival_set" | "concert_film" | "unknown"


@dataclass
class UpdateInfo:
    installed: str
    latest: str | None
    behind: bool


@dataclass
class RunReport:
    channel: str                       # "new_sets" | "updated_sets"
    sets: list[EmailSet]
    update: UpdateInfo | None
    stats: dict                        # {"added": int, "up_to_date": int, "errors": int}
    timestamp: str


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (cid, jpeg bytes)


@dataclass
class SMTPSettings:
    host: str
    port: int
    security: str          # "starttls" | "ssl" | "none"
    user: str
    password: str
    from_address: str
