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

    # Folder-level files that belong to the folder, not individual videos.
    FOLDER_LEVEL_FILES = frozenset({"folder.jpg", "fanart.jpg", "album.nfo"})

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.executor import resolve_collision
        import shutil

        target = resolve_collision(self.target)
        target.parent.mkdir(parents=True, exist_ok=True)

        old_stem = file_path.stem
        old_dir = file_path.parent

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

            # Move sidecar files that share the video's stem
            new_stem = target.stem
            self._move_sidecars(old_dir, old_stem, target.parent, new_stem,
                                shutil, self.action)

            return OperationResult(self.name, "done")
        except OSError as e:
            return OperationResult(self.name, "error", str(e))

    def _move_sidecars(self, old_dir: Path, old_stem: str,
                       new_dir: Path, new_stem: str,
                       shutil, action: str) -> None:
        """Move/copy sidecar files from old_dir to new_dir, renaming stems."""
        # Collect sidecars: {old_stem}.* (exact stem match) and {old_stem}-*
        sidecars: list[Path] = []
        for candidate in old_dir.iterdir():
            if candidate.name in self.FOLDER_LEVEL_FILES:
                continue
            name = candidate.name
            if name.startswith(old_stem + ".") or name.startswith(old_stem + "-"):
                # Skip the video file itself (already moved)
                if not candidate.exists():
                    continue
                sidecars.append(candidate)

        for sidecar in sidecars:
            # Compute new name: replace old_stem prefix with new_stem
            suffix = sidecar.name[len(old_stem):]  # e.g. ".nfo" or "-poster.jpg"
            new_name = new_stem + suffix
            new_path = new_dir / new_name

            try:
                if action == "copy":
                    shutil.copy2(sidecar, new_path)
                elif action == "rename":
                    sidecar.rename(new_path)
                else:
                    shutil.move(str(sidecar), str(new_path))
                logger.debug("Sidecar %s: %s -> %s", action, sidecar.name, new_path.name)
            except OSError as e:
                logger.warning("Failed to %s sidecar %s: %s", action, sidecar.name, e)


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
                detail=mf.stage or "",
                venue=mf.venue or "",
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
        self._logo_hits: dict[str, Path] = {}   # festival -> logo path
        self._logo_misses: set[str] = set()      # festivals without curated logo

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        folder = file_path.parent
        if folder in self._completed_folders:
            return False
        folder_jpg = folder / "folder.jpg"
        if self.force:
            return True
        return not folder_jpg.exists()

    def _get_folder_poster_type(self, content_type: str) -> str:
        """Determine poster type from the first segment of the layout template.

        Priority for mixed segments: {festival} > {artist} > {year}.
        """
        template = self.config.get_layout_template(content_type)
        first_segment = template.split("/")[0]
        return self._classify_segment(first_segment)

    def _get_layout_segments(self, content_type: str) -> list[str]:
        """Return poster type for each segment of the layout template."""
        template = self.config.get_layout_template(content_type)
        return [self._classify_segment(seg) for seg in template.split("/")]

    def _get_poster_type_for_folder(self, folder: Path, content_type: str) -> str:
        """Determine poster type for a specific folder depth in a nested layout."""
        if not self.library_root:
            return self._get_folder_poster_type(content_type)
        segments = self._get_layout_segments(content_type)
        try:
            depth = len(folder.resolve().relative_to(self.library_root.resolve()).parts) - 1
        except ValueError:
            depth = 0
        if depth < 0:
            depth = 0
        if depth < len(segments):
            return segments[depth]
        return segments[-1] if segments else "artist"

    @staticmethod
    def _classify_segment(segment: str) -> str:
        """Classify a template segment by priority: festival > artist > year."""
        if "{festival}" in segment:
            return "festival"
        if "{artist}" in segment:
            return "artist"
        if "{year}" in segment:
            return "year"
        return "artist"

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

    def _download_artwork(self, url: str, cache_subdir: str, max_width: int | None = None) -> Path | None:
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
            if max_width:
                from PIL import Image
                with Image.open(cached) as img:
                    if img.width > max_width:
                        ratio = max_width / img.width
                        new_size = (max_width, int(img.height * ratio))
                        img = img.resize(new_size, Image.LANCZOS)
                        img.save(cached)
            logger.info("Downloaded artwork: %s -> %s", url, cached.name)
            return cached
        except (requests.RequestException, OSError) as e:
            logger.debug("Artwork download failed: %s", e)
            return None

    def _find_curated_logo(self, festival: str) -> Path | None:
        """Find curated festival logo from library or user-level folders."""
        canonical = self.config.resolve_festival_alias(festival) if festival else ""
        if not canonical:
            return None

        search_dirs: list[Path] = []
        if self.library_root:
            search_dirs.append(self.library_root / ".cratedigger" / "festivals" / canonical)
        search_dirs.append(Path.home() / ".cratedigger" / "festivals" / canonical)

        for d in search_dirs:
            for ext in ("jpg", "jpeg", "png", "webp"):
                candidate = d / f"logo.{ext}"
                if candidate.exists():
                    logger.info("Curated logo: %s", candidate)
                    return candidate
        return None

    def _find_dj_artwork(self, folder: Path) -> Path | None:
        """Find DJ artwork URL from media files in folder, download and cache."""
        from festival_organizer.analyzer import analyse_file
        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                mf = analyse_file(video, folder, self.config)
                logger.debug("Album poster: dj_artwork_url=%s", mf.dj_artwork_url or "(empty)")
                if mf.dj_artwork_url:
                    return self._download_artwork(mf.dj_artwork_url, "dj-artwork", max_width=600)
                # Fallback: fetch DJ artwork from tracklist page
                if mf.tracklists_url:
                    result = self._fetch_dj_artwork_from_tracklist(mf.tracklists_url)
                    if result:
                        return result
        return None

    def _fetch_dj_artwork_from_tracklist(self, tracklist_url: str) -> Path | None:
        """Fetch DJ artwork by scraping a 1001TL tracklist page for DJ slugs.

        Returns local cached path or None on failure.
        """
        try:
            email, password = self.config.tracklists_credentials
            if not email or not password:
                logger.debug("No 1001TL credentials, skipping DJ artwork fallback")
                return None

            from festival_organizer.tracklists.api import TracklistSession, _extract_dj_slugs
            api = TracklistSession()
            api.login(email, password)
            resp = api._request("GET", tracklist_url)
            slugs = _extract_dj_slugs(resp.text)
            if not slugs:
                logger.debug("No DJ slugs found on tracklist page")
                return None

            dj_artwork_url = api._fetch_dj_artwork(slugs[0])
            if not dj_artwork_url:
                logger.debug("No DJ artwork found for slug %s", slugs[0])
                return None

            return self._download_artwork(dj_artwork_url, "dj-artwork", max_width=600)
        except Exception as e:
            logger.debug("DJ artwork fallback failed: %s", e)
            return None

    def _resolve_background(self, priority: list[str], folder: Path,
                             media_file: MediaFile) -> Path | None:
        """Walk the background priority chain, return first successful image."""
        tried_curated = False
        for source in priority:
            bg = self._try_background_source(source, folder, media_file)
            if source == "curated_logo":
                tried_curated = True
                if bg and media_file.festival:
                    canonical = self.config.resolve_festival_alias(media_file.festival)
                    self._logo_hits[canonical] = bg
            if bg:
                logger.info("Album poster: using %s", source)
                return bg
            logger.debug("Album poster: %s not available", source)
        if tried_curated and media_file.festival:
            canonical = self.config.resolve_festival_alias(media_file.festival)
            if canonical not in self._logo_hits:
                self._logo_misses.add(canonical)
        return None

    def _try_background_source(self, source: str, folder: Path,
                                media_file: MediaFile) -> Path | None:
        """Try a single background source. Returns path or None."""
        if source == "curated_logo":
            return self._find_curated_logo(media_file.festival)
        elif source == "dj_artwork":
            return self._find_dj_artwork(folder)
        elif source == "fanart_tv":
            return self._find_fanart_background(folder, media_file.artist)
        elif source == "thumb_collage":
            return None  # Handled by generate_album_poster via thumb_paths
        elif source == "gradient":
            return None  # No image needed, poster generator creates gradient
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

            # Determine poster type from layout template
            poster_type = self._get_folder_poster_type(mf.content_type)
            logger.debug("Album poster: type=%s (from layout template)", poster_type)

            # Walk configurable background priority chain
            ps = self.config.poster_settings
            if poster_type == "artist":
                priority = ps.get("artist_background_priority",
                                  ["dj_artwork", "fanart_tv", "gradient"])
            elif poster_type == "festival":
                priority = ps.get("festival_background_priority",
                                  ["curated_logo", "thumb_collage", "gradient"])
            else:  # year
                priority = ps.get("year_background_priority", ["gradient"])

            bg_path = self._resolve_background(priority, file_path.parent, mf)

            # Determine hero_text and festival/title based on poster type
            if poster_type == "artist":
                hero_text = mf.artist
                poster_title = festival_display or mf.artist or "Unknown"
            elif poster_type == "festival":
                hero_text = None
                poster_title = festival_display or mf.artist or "Unknown"
            else:  # year
                hero_text = date_or_year or mf.year
                poster_title = festival_display or mf.artist or "Unknown"

            generate_album_poster(
                output_path=folder_jpg,
                festival=poster_title,
                date_or_year=date_or_year,
                detail=mf.stage or mf.location or "",
                thumb_paths=thumb_paths if thumb_paths else None,
                background_image_path=bg_path,
                hero_text=hero_text,
            )
            self._completed_folders.add(file_path.parent)
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))

    def logo_summary(self) -> list[str]:
        """Return summary lines about curated logo usage."""
        lines: list[str] = []
        if self._logo_hits:
            lines.append(f"Curated logos used: {len(self._logo_hits)}")
            for fest, path in sorted(self._logo_hits.items()):
                lines.append(f"  {fest}: {path}")
        if self._logo_misses:
            lines.append(f"Missing curated logos: {len(self._logo_misses)}")
            for fest in sorted(self._logo_misses):
                lines.append(f"  {fest}")
        # Check for unmatched folders in .cratedigger/festivals/
        if self.library_root:
            festivals_dir = self.library_root / ".cratedigger" / "festivals"
            if festivals_dir.is_dir():
                known = set(self._logo_hits.keys()) | self._logo_misses
                for d in sorted(festivals_dir.iterdir()):
                    if d.is_dir() and d.name not in known:
                        lines.append(f"  Unmatched folder: {d.name}")
        return lines


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
        for artist in split_artists(media_file.artist, groups=self.config.artist_groups):
            if artist in self._completed_artists:
                continue
            d = self._artist_dir(artist)
            if self.force:
                return True
            if not (d / "clearlogo.png").exists() or not (d / "fanart.jpg").exists():
                return True
        return False

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.fanart import (
            split_artists, download_artist_images, lookup_mbid,
            fetch_artist_images, pick_best_logo, pick_best_background,
        )
        artists = split_artists(media_file.artist, groups=self.config.artist_groups)
        fetched = []
        for artist in artists:
            if artist in self._completed_artists:
                continue
            d = self._artist_dir(artist)
            try:
                # Look up MBID and store on MediaFile
                mbid = lookup_mbid(artist, self._get_cache())
                if mbid and not media_file.mbid:
                    media_file.mbid = mbid

                # Fetch fanart.tv data once — extract URLs and pass to downloader
                fanart_data = None
                if mbid:
                    fanart_data = fetch_artist_images(
                        mbid,
                        self.config.fanart_project_api_key,
                        self.config.fanart_personal_api_key,
                    )
                    if fanart_data:
                        logo = pick_best_logo(fanart_data.get("hdmusiclogo", []))
                        if logo and not media_file.clearlogo_url:
                            media_file.clearlogo_url = logo["url"]
                        bg = pick_best_background(fanart_data.get("artistbackground", []))
                        if bg and not media_file.fanart_url:
                            media_file.fanart_url = bg["url"]

                logo_ok, bg_ok = download_artist_images(
                    artist, d,
                    self.config.fanart_project_api_key,
                    self.config.fanart_personal_api_key,
                    self._get_cache(),
                    force=self.force,
                    prefetched_mbid=mbid,
                    prefetched_data=fanart_data,
                )
                self._completed_artists.add(artist)
                if logo_ok or bg_ok:
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
        from festival_organizer.mkv_tags import MATROSKA_EXTS
        if file_path.suffix.lower() not in MATROSKA_EXTS:
            return False
        # embed_tags compares desired vs existing tags and skips the write
        # when nothing changed, so always return True here.
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
