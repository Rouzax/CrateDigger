"""Composable operations with gap detection.

Logging:
    Logger: 'festival_organizer.operations'
    Key events:
        - album_poster.style (INFO): Album poster style decision (artist vs festival)
    See docs/logging.md for full guidelines.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

from festival_organizer.config import Config
from festival_organizer.models import MediaFile

logger = logging.getLogger(__name__)


@dataclass
class OperationResult:
    """Result of a single operation execution."""
    name: str
    status: str  # "done", "skipped", "error"
    detail: str = ""


class Operation:
    """Base class for operations."""
    name: str = ""

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        """Check if this operation needs to run (gap detection)."""
        raise NotImplementedError

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        """Execute the operation. Returns result."""
        raise NotImplementedError


class OrganizeOperation(Operation):
    name = "organize"

    def __init__(self, target: Path, action: str = "move"):
        self.target = target
        self.action = action  # "move", "copy", "rename"

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        return file_path.resolve() != self.target.resolve()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.executor import resolve_collision
        import shutil

        target = resolve_collision(self.target)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self.action == "copy":
                shutil.copy2(file_path, target)
            elif self.action == "rename":
                file_path.rename(target)
            else:
                shutil.move(str(file_path), str(target))
            # Update target so downstream operations (nfo, art, etc.) use the
            # resolved path. This mutation is read by run_pipeline() — requires
            # serial execution; do not reuse operation instances across files.
            self.target = target
            return OperationResult(self.name, "done")
        except OSError as e:
            return OperationResult(self.name, "error", str(e))


class NfoOperation(Operation):
    name = "nfo"

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        return not file_path.with_suffix(".nfo").exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.nfo import generate_nfo
        try:
            generate_nfo(media_file, file_path, self.config)
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))


class ArtOperation(Operation):
    name = "art"

    def __init__(self, force: bool = False):
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
        return not thumb.exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.artwork import extract_cover
        try:
            result = extract_cover(file_path, file_path.parent)
            if result:
                return OperationResult(self.name, "done")
            return OperationResult(self.name, "error", "no embedded art, no frames")
        except (OSError, subprocess.SubprocessError) as e:
            return OperationResult(self.name, "error", str(e))


class PosterOperation(Operation):
    name = "poster"

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
        if not thumb.exists():
            return False  # Can't generate without thumb
        if self.force:
            return True
        poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
        return not poster.exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.poster import generate_set_poster
        try:
            thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
            poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
            mf = media_file
            festival_display = mf.festival
            if mf.location:
                festival_display = self.config.get_festival_display(
                    mf.festival, mf.location
                )
            generate_set_poster(
                source_image_path=thumb,
                output_path=poster,
                artist=mf.artist or "Unknown",
                festival=festival_display or mf.title or "",
                date=mf.date,
                year=mf.year,
                detail=mf.stage or mf.location or "",
            )
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))


class AlbumPosterOperation(Operation):
    name = "album_poster"

    def __init__(self, config: Config, force: bool = False, library_root: Path | None = None):
        self.config = config
        self.force = force
        self.library_root = library_root
        self._completed_folders: set[Path] = set()

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        folder = file_path.parent
        if folder in self._completed_folders:
            return False
        folder_jpg = folder / "folder.jpg"
        if self.force:
            return True
        return not folder_jpg.exists()

    def _find_fanart_background(self, folder: Path, artist: str) -> Path | None:
        """Find a fanart.tv background for an artist folder.

        Only returns a background if the folder contains a single artist —
        multi-artist folders (festival folders) use gradient backgrounds instead.
        """
        if not self.library_root or not artist:
            return None

        # Check if this is a single-artist folder by scanning filenames
        # Use parent folder name heuristic: if folder name matches artist, it's an artist folder
        # Otherwise scan thumbs for artist diversity
        from festival_organizer.parsers import parse_filename
        from festival_organizer.normalization import normalise_name
        artists_in_folder: set[str] = set()
        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                parsed = parse_filename(video, self.config)
                if parsed.get("artist"):
                    artists_in_folder.add(normalise_name(parsed["artist"]).lower())
                if len(artists_in_folder) > 1:
                    logger.info("Album poster: %d artists in folder -> festival style",
                                len(artists_in_folder))
                    return None  # Multi-artist folder, skip fanart background

        # Single artist (or couldn't determine) — look for their fanart
        safe = "".join(
            c if c.isalnum() or c in " ._-()&" else "_" for c in artist
        ).strip()
        candidate = self.library_root / ".cratedigger" / "artists" / safe / "fanart.jpg"
        result = candidate if candidate.exists() else None
        logger.info("Album poster: 1 artist in folder -> %s",
                    "artist style" if result else "festival style (no fanart)")
        return result

    def _download_artwork(self, url: str, cache_subdir: str) -> Path | None:
        """Download an artwork URL to cache. Returns local path or None."""
        if not url or not self.library_root:
            return None
        h = hashlib.md5(url.encode()).hexdigest()[:12]
        ext = url.rsplit(".", 1)[-1].split("?")[0][:4]
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        cache_dir = self.library_root / ".cratedigger" / cache_subdir
        cached = cache_dir / f"{h}.{ext}"
        if cached.exists():
            return cached
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(resp.content)
            logger.info("Downloaded artwork: %s -> %s", url, cached.name)
            return cached
        except (requests.RequestException, OSError) as e:
            logger.debug("Artwork download failed: %s", e)
            return None

    def _find_event_artwork(self, folder: Path) -> Path | None:
        """Find event artwork URL from media files in folder, download and cache."""
        from festival_organizer.analyzer import analyse_file
        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                mf = analyse_file(video, folder, self.config)
                if mf.event_artwork_url:
                    return self._download_artwork(mf.event_artwork_url, "events")
        return None

    def _find_dj_artwork(self, folder: Path) -> Path | None:
        """Find DJ artwork URL from media files in folder, download and cache."""
        from festival_organizer.analyzer import analyse_file
        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                mf = analyse_file(video, folder, self.config)
                if mf.dj_artwork_url:
                    return self._download_artwork(mf.dj_artwork_url, "dj-artwork")
        return None

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.poster import generate_album_poster
        try:
            folder_jpg = file_path.parent / "folder.jpg"
            mf = media_file
            festival_display = mf.festival
            if mf.location:
                festival_display = self.config.get_festival_display(
                    mf.festival, mf.location
                )
            # Determine year: scan folder for consensus, omit if mixed
            from festival_organizer.parsers import parse_filename
            years_in_folder: set[str] = set()
            for video in file_path.parent.iterdir():
                if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                    parsed = parse_filename(video, self.config)
                    yr = parsed.get("year", "")
                    if yr:
                        years_in_folder.add(yr)
            if len(years_in_folder) == 1:
                date_or_year = years_in_folder.pop()
            else:
                date_or_year = ""

            # Collect existing thumbs in folder for color extraction
            thumb_paths = list(file_path.parent.glob("*-thumb.jpg"))

            # Determine if this is a single-artist or multi-artist (festival) folder
            fanart_path = self._find_fanart_background(file_path.parent, mf.artist)
            is_artist_folder = fanart_path is not None

            # Background image fallback chain
            bg_path = None

            if is_artist_folder and self.library_root and mf.dj_artwork_url:
                # Artist folder: prefer fresh 1001TL DJ artwork over fanart.tv
                dj_art = self._download_artwork(mf.dj_artwork_url, "dj-artwork")
                if dj_art:
                    bg_path = dj_art
                    logger.info("Album poster: using DJ artwork (1001TL)")

            if not bg_path and is_artist_folder:
                # Artist folder: fall back to fanart.tv
                bg_path = fanart_path

            if not bg_path and self.library_root and mf.event_artwork_url:
                # Festival folder: try event artwork
                event_art = self._download_artwork(mf.event_artwork_url, "events")
                if event_art:
                    bg_path = event_art
                    logger.info("Album poster: using event artwork")

            if not bg_path and not is_artist_folder and self.library_root and mf.dj_artwork_url:
                # Festival folder without event artwork: try DJ artwork
                dj_art = self._download_artwork(mf.dj_artwork_url, "dj-artwork")
                if dj_art:
                    bg_path = dj_art
                    logger.info("Album poster: using DJ artwork")

            generate_album_poster(
                output_path=folder_jpg,
                festival=festival_display or mf.artist or "Unknown",
                date_or_year=date_or_year,
                detail=mf.stage or mf.location or "",
                thumb_paths=thumb_paths if thumb_paths else None,
                background_image_path=bg_path,
                hero_text=mf.artist if is_artist_folder else None,
            )
            self._completed_folders.add(file_path.parent)
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))


class FanartOperation(Operation):
    """Download artist artwork from fanart.tv.

    This operation is shared across all files in a pipeline run to deduplicate
    API calls when multiple files share an artist. The _completed_artists set
    tracks which artists have already been processed.
    """
    name = "fanart"

    def __init__(self, config: Config, library_root: Path, force: bool = False):
        self.config = config
        self.library_root = library_root
        self.force = force
        self._completed_artists: set[str] = set()
        self._cache = None

    def _get_cache(self):
        if self._cache is None:
            from festival_organizer.fanart import MBIDCache
            self._cache = MBIDCache()
        return self._cache

    def _artist_dir(self, artist: str) -> Path:
        """Resolve per-artist directory at library root level."""
        safe = "".join(c if c.isalnum() or c in " ._-()&" else "_" for c in artist).strip()
        return self.library_root / ".cratedigger" / "artists" / safe

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if not self.config.fanart_enabled or not self.config.fanart_project_api_key:
            return False
        if not media_file.artist:
            return False
        from festival_organizer.fanart import split_artists
        for artist in split_artists(media_file.artist):
            if artist in self._completed_artists:
                continue
            d = self._artist_dir(artist)
            if self.force:
                return True
            if not (d / "clearlogo.png").exists() or not (d / "fanart.jpg").exists():
                return True
        return False

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.fanart import split_artists, download_artist_images
        artists = split_artists(media_file.artist)
        fetched = []
        for artist in artists:
            if artist in self._completed_artists:
                continue
            d = self._artist_dir(artist)
            try:
                logo, bg = download_artist_images(
                    artist, d,
                    self.config.fanart_project_api_key,
                    self.config.fanart_personal_api_key,
                    self._get_cache(),
                    force=self.force,
                )
                self._completed_artists.add(artist)
                if logo or bg:
                    fetched.append(artist)
            except Exception as e:
                return OperationResult(self.name, "error", f"{artist}: {e}")
        if fetched:
            return OperationResult(self.name, "done", f"fetched for: {', '.join(fetched)}")
        return OperationResult(self.name, "skipped", "already cached or not available")


class TagsOperation(Operation):
    name = "tags"

    def __init__(self, force: bool = False):
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        # Only MKV/WEBM support tag embedding
        if file_path.suffix.lower() not in (".mkv", ".webm"):
            return False
        # No gap detection: reading existing MKV tags to compare is expensive
        # and mkvpropedit is fast and idempotent, so always re-embed.
        return True

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.embed_tags import embed_tags
        try:
            success = embed_tags(media_file, file_path)
            if success:
                return OperationResult(self.name, "done")
            return OperationResult(self.name, "error", "embed_tags returned False")
        except (OSError, subprocess.SubprocessError) as e:
            return OperationResult(self.name, "error", str(e))
