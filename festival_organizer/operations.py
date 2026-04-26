"""Composable operations with gap detection.

Logging:
    Logger: 'festival_organizer.operations'
    Key events:
        - album_poster.style (INFO): Album poster style decision (artist vs festival)
        - dj_artwork.prepare (DEBUG): DJ artwork cropped/resized for centered layout
    See docs/logging.md for full guidelines.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from festival_organizer import paths
from festival_organizer.cache_ttl import hashed_jitter_factor
from festival_organizer.config import Config, _log_deprecated_once
from festival_organizer.fanart import lookup_mbid
from festival_organizer.models import MediaFile

logger = logging.getLogger(__name__)


@dataclass
class OperationResult:
    """Result of a single operation execution."""
    name: str
    status: str  # "done", "skipped", "error"
    detail: str = ""
    display_name: str = ""  # Per-file label; falls back to name if empty


class Operation:
    """Base class for operations."""
    name: str = ""
    display_name: str = ""  # Per-file label; falls back to name if empty

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
        self.sidecars_moved = 0

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        # Case-sensitive string compare: a canonical-casing rename such as
        # Alok -> ALOK must run even on case-insensitive filesystems, where
        # Path.resolve() would normalise both sides to the same string.
        return str(file_path) != str(self.target)

    # Folder-level files that belong to the folder, not individual videos.
    FOLDER_LEVEL_FILES = frozenset({"folder.jpg", "fanart.jpg"})

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.executor import resolve_collision
        import shutil

        target = resolve_collision(self.target, source=file_path)
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
            # resolved path. This mutation is read by run_pipeline(); requires
            # serial execution; do not reuse operation instances across files.
            self.target = target

            # Move sidecar files that share the video's stem
            new_stem = target.stem
            self.sidecars_moved = self._move_sidecars(
                old_dir, old_stem, target.parent, new_stem,
                shutil, self.action,
            )

            return OperationResult(self.name, "done")
        except OSError as e:
            return OperationResult(self.name, "error", str(e))

    def _move_sidecars(self, old_dir: Path, old_stem: str,
                       new_dir: Path, new_stem: str,
                       shutil, action: str) -> int:
        """Move/copy sidecar files from old_dir to new_dir, renaming stems."""
        moved = 0
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
                moved += 1
            except OSError as e:
                logger.warning("Failed to %s sidecar %s: %s", action, sidecar.name, e)
        return moved


class NfoOperation(Operation):
    name = "nfo"

    def __init__(self, config: Config, force: bool = False, dj_cache: object | None = None):
        self.config = config
        self.force = force
        self.dj_cache = dj_cache

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        return not file_path.with_suffix(".nfo").exists()

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.nfo import generate_nfo
        try:
            generate_nfo(media_file, file_path, self.config, dj_cache=self.dj_cache)
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
            if not result:
                return OperationResult(self.name, "error", "no art available")
            # Copy thumb as fanart sidecar (Kodi expects -fanart.jpg on disk)
            thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
            fanart = file_path.with_name(f"{file_path.stem}-fanart.jpg")
            if thumb.exists():
                shutil.copy2(thumb, fanart)
            return OperationResult(self.name, "done")
        except (OSError, subprocess.SubprocessError) as e:
            return OperationResult(self.name, "error", str(e))


class PosterOperation(Operation):
    name = "posters"
    display_name = "poster"

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
            festival_slot = mf.place
            if mf.edition:
                festival_slot = self.config.get_place_display(mf.place, mf.edition)
            venue_used_in_slot = mf.place_kind in ("venue", "location")
            venue_for_subline = "" if venue_used_in_slot else (mf.venue or "")
            generate_set_poster(
                source_image_path=thumb,
                output_path=poster,
                artist=mf.display_artist or mf.artist or "Unknown",
                festival=festival_slot,
                date=mf.date,
                year=mf.year,
                detail=mf.stage or "",
                venue=venue_for_subline,
            )
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))


class AlbumPosterOperation(Operation):
    name = "posters"
    display_name = "album_poster"

    def __init__(self, config: Config, force: bool = False, library_root: Path | None = None,
                 ttl_days: int = 90):
        self.config = config
        self.force = force
        self.library_root = library_root
        self._ttl_days = ttl_days
        self._completed_folders: set[Path] = set()
        self._logo_hits: dict[str, Path] = {}   # place -> logo path
        self._logo_misses: set[str] = set()      # places without curated logo

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        folder = file_path.parent
        if folder in self._completed_folders:
            return False
        folder_jpg = folder / "folder.jpg"
        if self.force:
            return True
        return not folder_jpg.exists()

    def _get_folder_poster_type(self, mf: MediaFile) -> str:
        """Determine poster type from the first segment of the layout template.

        Priority for mixed segments: {place}/{festival} > {artist} > {year}.
        When the layout's first segment resolves to "festival" but the runtime
        place_kind is "artist" (no festival/venue/location matched), the poster
        type falls back to "artist" so the artist background pipeline runs.
        """
        template = self.config.get_layout_template(mf.content_type)
        first_segment = template.split("/")[0]
        base = self._classify_segment(first_segment)
        if base == "festival" and mf.place_kind == "artist":
            return "artist"
        return base

    def _get_layout_segments(self, content_type: str) -> list[str]:
        """Return poster type for each segment of the layout template."""
        template = self.config.get_layout_template(content_type)
        return [self._classify_segment(seg) for seg in template.split("/")]

    def _get_poster_type_for_folder(self, folder: Path, mf: MediaFile) -> str:
        """Determine poster type for a specific folder depth in a nested layout."""
        if not self.library_root:
            return self._get_folder_poster_type(mf)
        segments = self._get_layout_segments(mf.content_type)
        try:
            depth = len(folder.resolve().relative_to(self.library_root.resolve()).parts) - 1
        except ValueError:
            depth = 0
        if depth < 0:
            depth = 0
        if depth < len(segments):
            base = segments[depth]
        else:
            base = segments[-1] if segments else "artist"
        if base == "festival" and mf.place_kind == "artist":
            return "artist"
        return base

    @staticmethod
    def _classify_segment(segment: str) -> str:
        """Classify a template segment by priority: place/festival > artist > year.

        The {place} and {festival} tokens are interchangeable for classification purposes.
        {festival} is the deprecated alias kept for backward compatibility through 1.0.0.
        """
        if "{place}" in segment or "{festival}" in segment:
            return "festival"
        if "{artist}" in segment:
            return "artist"
        if "{year}" in segment:
            return "year"
        return "artist"

    def _find_fanart_background(self, folder: Path, artist: str) -> Path | None:
        """Find a fanart.tv background for an artist folder.

        Only returns a background if the folder contains a single artist;
        multi-artist folders (festival folders) use gradient backgrounds instead.
        """
        if not artist:
            return None

        # Check if this is a single-artist folder by scanning filenames
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

        # Single artist (or couldn't determine); look for their fanart
        candidate = paths.artist_cache_dir(artist) / "fanart.jpg"
        result = candidate if candidate.exists() else None
        logger.info("Album poster: 1 artist in folder -> %s",
                    "artist style" if result else "festival style (no fanart)")
        return result

    def _download_artwork(self, url: str, cache_subdir: str, max_width: int | None = None) -> Path | None:
        """Download an artwork URL to cache. Returns local path or None."""
        if not url:
            return None
        h = hashlib.md5(url.encode()).hexdigest()[:12]
        ext = url.rsplit(".", 1)[-1].split("?")[0][:4]
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        artwork_cache_dir = paths.cache_dir() / cache_subdir
        cached = artwork_cache_dir / f"{h}.{ext}"
        if cached.exists():
            age_days = (time.time() - cached.stat().st_mtime) / 86400
            effective_ttl = self._ttl_days * hashed_jitter_factor(cached.name)
            if age_days <= effective_ttl:
                return cached
            cached.unlink()
            logger.debug("Stale artwork cache (%d days, ttl %.1f): %s",
                         int(age_days), effective_ttl, cached.name)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            paths.ensure_parent(cached)
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

    def _download_dj_artwork(self, url: str, artist: str) -> Path | None:
        """Download DJ artwork, convert to JPEG, crop/resize, save to artist dir."""
        if not url or not artist:
            return None
        artist_dir = paths.artist_cache_dir(artist)
        cached = artist_dir / "dj-artwork.jpg"
        if cached.exists():
            age_days = (time.time() - cached.stat().st_mtime) / 86400
            effective_ttl = self._ttl_days * hashed_jitter_factor(cached.name)
            if age_days <= effective_ttl:
                return cached
            cached.unlink()
            logger.debug("Stale DJ artwork cache (%d days, ttl %.1f): %s",
                         int(age_days), effective_ttl, artist)
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            artist_dir.mkdir(parents=True, exist_ok=True)
            from PIL import Image
            import io
            with Image.open(io.BytesIO(resp.content)) as img:
                img = img.convert("RGB")
                w, h = img.size
                if w != h:
                    side = min(w, h)
                    left = (w - side) // 2
                    top = (h - side) // 2
                    img = img.crop((left, top, left + side, top + side))
                    logger.debug("DJ artwork: center-cropped %dx%d -> %dx%d", w, h, side, side)
                max_side = 550
                if img.width > max_side:
                    img = img.resize((max_side, max_side), Image.LANCZOS)
                    logger.debug("DJ artwork: resized -> %dx%d", max_side, max_side)
                img.save(cached, "JPEG", quality=90)
            logger.info("Downloaded DJ artwork: %s -> %s", artist, cached)
            return cached
        except (requests.RequestException, OSError) as e:
            logger.debug("DJ artwork download failed for %s: %s", artist, e)
            return None

    def _find_curated_logo(self, place: str, edition: str = "") -> Path | None:
        """Find curated logo for a place from library or user-level folders.

        Library lookup prefers ``.cratedigger/places/<name>/`` and falls back to
        the legacy ``.cratedigger/festivals/<name>/`` directory for backward
        compatibility, emitting a one-shot deprecation warning when the legacy
        path is used. Tries edition-specific path first (e.g.,
        ``places/EDC Las Vegas/logo.png``), then falls back to canonical
        (e.g., ``places/EDC/logo.png``).
        """
        canonical = self.config.resolve_place_alias(place) if place else ""
        if not canonical:
            return None

        names = []
        if edition:
            display = self.config.get_place_display(canonical, edition)
            if display != canonical:
                names.append(display)
        names.append(canonical)

        for name in names:
            search_dirs: list[tuple[Path, bool]] = []
            if self.library_root:
                search_dirs.append(
                    (self.library_root / ".cratedigger" / "places" / name, False)
                )
                search_dirs.append(
                    (self.library_root / ".cratedigger" / "festivals" / name, True)
                )
            search_dirs.append((paths.festivals_logo_dir() / name, False))
            for d, is_legacy in search_dirs:
                for ext in ("jpg", "jpeg", "png", "webp"):
                    candidate = d / f"logo.{ext}"
                    if candidate.exists():
                        if is_legacy:
                            _log_deprecated_once(
                                ".cratedigger/festivals dir",
                                "Curated logo found under .cratedigger/festivals/; "
                                "this directory is deprecated, move logos to "
                                ".cratedigger/places/. Support for "
                                ".cratedigger/festivals/ will be removed in 1.0.0.",
                            )
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
                if mf.dj_artwork_url and mf.artist:
                    result = self._download_dj_artwork(mf.dj_artwork_url, mf.artist)
                    if result:
                        return result
                # Fallback: fetch DJ artwork from tracklist page
                if mf.tracklists_url and mf.artist:
                    result = self._fetch_dj_artwork_from_tracklist(mf.tracklists_url, mf.artist)
                    if result:
                        return result
        return None

    def _warm_dj_artwork_cache(self, folder: Path) -> None:
        """Download DJ artwork for all artists in a folder."""
        from festival_organizer.analyzer import analyse_file
        seen: set[str] = set()
        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                mf = analyse_file(video, folder, self.config)
                if not mf.artist or mf.artist in seen:
                    continue
                seen.add(mf.artist)
                if mf.dj_artwork_url:
                    self._download_dj_artwork(mf.dj_artwork_url, mf.artist)

    def _fetch_dj_artwork_from_tracklist(self, tracklist_url: str, artist: str) -> Path | None:
        """Fetch DJ artwork by scraping a 1001TL tracklist page for DJ slugs.

        Returns local cached path or None on failure.
        """
        try:
            email, password = self.config.tracklists_credentials
            if not email or not password:
                logger.debug("No 1001TL credentials, skipping DJ artwork fallback")
                return None

            from festival_organizer.tracklists.api import TracklistSession, _extract_dj_slugs
            from festival_organizer.tracklists import canary
            api = TracklistSession()
            api.login(email, password)
            resp = api._request("GET", tracklist_url)
            api._run_canary(
                "tracklist page",
                canary.check_tracklist_page(resp.text),
                tracklist_url,
            )
            slugs = _extract_dj_slugs(resp.text)
            if not slugs:
                logger.debug("No DJ slugs found on tracklist page")
                return None

            profile = api._fetch_dj_profile(slugs[0])
            dj_artwork_url = profile["artwork_url"]
            if not dj_artwork_url:
                logger.debug("No DJ artwork found for slug %s", slugs[0])
                return None

            return self._download_dj_artwork(dj_artwork_url, artist)
        except Exception as e:
            logger.debug("DJ artwork fallback failed: %s", e)
            return None

    def _resolve_background(self, priority: list[str], folder: Path,
                             media_file: MediaFile) -> tuple[Path | None, str]:
        """Walk the background priority chain, return first successful image and source name."""
        tried_curated = False
        for source in priority:
            bg = self._try_background_source(source, folder, media_file)
            if source == "curated_logo":
                tried_curated = True
                if bg and media_file.place:
                    display = self.config.get_place_display(
                        media_file.place, media_file.edition)
                    self._logo_hits[display] = bg
            if bg:
                logger.info("Album poster: using %s", source)
                return bg, source
            logger.debug("Album poster: %s not available", source)
        if tried_curated and media_file.place:
            display = self.config.get_place_display(
                media_file.place, media_file.edition)
            if display not in self._logo_hits:
                self._logo_misses.add(display)
        return None, ""

    def _try_background_source(self, source: str, folder: Path,
                                media_file: MediaFile) -> Path | None:
        """Try a single background source. Returns path or None."""
        if source == "curated_logo":
            return self._find_curated_logo(media_file.place, media_file.edition)
        elif source == "dj_artwork":
            return self._find_dj_artwork(folder)
        elif source == "fanart_tv":
            return self._find_fanart_background(folder, media_file.artist)
        elif source == "gradient":
            return None  # No image needed, poster generator creates gradient
        return None

    def _get_priority_chain_for_poster_type(self, poster_type: str) -> list[str]:
        ps = self.config.poster_settings
        if poster_type == "artist":
            return ps.get("artist_background_priority",
                          ["dj_artwork", "fanart_tv", "gradient"])
        if poster_type == "festival":
            return ps.get("place_background_priority",
                          ["curated_logo", "gradient"])
        return ps.get("year_background_priority", ["gradient"])

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.poster import generate_album_poster
        try:
            folder_jpg = file_path.parent / "folder.jpg"
            mf = media_file
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
            poster_type = self._get_folder_poster_type(mf)
            logger.debug("Album poster: type=%s (from layout template)", poster_type)

            # Walk configurable background priority chain
            priority = self._get_priority_chain_for_poster_type(poster_type)

            bg_path, bg_source = self._resolve_background(priority, file_path.parent, mf)

            # Warm caches for background sources not in this poster's priority chain
            untried = {"curated_logo", "fanart_tv"} - set(priority)
            for source in untried:
                self._try_background_source(source, file_path.parent, mf)
            # DJ artwork: always warm for ALL artists in folder, not just the first
            self._warm_dj_artwork_cache(file_path.parent)

            # Look up brand color keyed by canonical place
            fc = self.config.place_config.get(mf.place, {})
            color_hex = fc.get("editions", {}).get(mf.edition, {}).get("color") or fc.get("color")
            if color_hex:
                from festival_organizer.poster import _hex_to_rgb
                override_color = _hex_to_rgb(color_hex)
            else:
                override_color = None

            poster_festival = mf.place or "Unknown"
            hero_text = mf.artist if poster_type == "artist" else (
                date_or_year or mf.year if poster_type == "year" else None
            )

            generate_album_poster(
                output_path=folder_jpg,
                festival=poster_festival,
                date_or_year=date_or_year,
                detail=mf.stage or "",
                edition=mf.edition or "",
                thumb_paths=thumb_paths if thumb_paths else None,
                override_color=override_color,
                background_image_path=bg_path,
                background_source=bg_source,
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
            for place, path in sorted(self._logo_hits.items()):
                lines.append(f"  {place}: {path}")
        if self._logo_misses:
            lines.append(f"Missing curated logos: {len(self._logo_misses)}")
            for place in sorted(self._logo_misses):
                lines.append(f"  {place}")
        if self.library_root:
            known = set(self._logo_hits.keys()) | self._logo_misses
            seen_dirs: set[str] = set()
            for sub in ("places", "festivals"):
                logo_root = self.library_root / ".cratedigger" / sub
                if not logo_root.is_dir():
                    continue
                for d in sorted(logo_root.iterdir()):
                    if d.is_dir() and d.name not in known and d.name not in seen_dirs:
                        seen_dirs.add(d.name)
                        lines.append(f"  Unmatched folder: {d.name}")
        return lines


class FanartOperation(Operation):
    """Download artist artwork from fanart.tv.

    This operation is shared across all files in a pipeline run to deduplicate
    API calls when multiple files share an artist. The _completed_artists set
    tracks which artists have already been processed.
    """
    name = "fanart"

    def __init__(self, config: Config, library_root: Path, force: bool = False,
                 ttl_days: int = 90):
        self.config = config
        self.library_root = library_root
        self.force = force
        self._ttl_days = ttl_days
        self._completed_artists: set[str] = set()
        self._cache = None

    def _get_cache(self):
        if self._cache is None:
            from festival_organizer.fanart import MBIDCache
            ttl = self.config.cache_ttl.get("mbid_days", 90)
            self._cache = MBIDCache(ttl_days=ttl)
        return self._cache

    def _is_stale(self, path: Path) -> bool:
        """Check if a cached file is missing or older than jittered TTL."""
        if not path.exists():
            return True
        age_days = (time.time() - path.stat().st_mtime) / 86400
        effective_ttl = self._ttl_days * hashed_jitter_factor(path.name)
        return age_days > effective_ttl

    def _artist_dir(self, artist: str) -> Path:
        """Resolve per-artist directory."""
        return paths.artist_cache_dir(artist)

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
            if self._is_stale(d / "clearlogo.png") or self._is_stale(d / "fanart.jpg"):
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
                mbid = lookup_mbid(artist, self._get_cache())

                # Fetch fanart.tv data once, extract URLs and pass to downloader
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
            status = embed_tags(media_file, file_path)
            if status == "error":
                return OperationResult(self.name, "error", "tag embedding failed")
            return OperationResult(self.name, status)
        except (OSError, subprocess.SubprocessError) as e:
            return OperationResult(self.name, "error", str(e))


def _extract_chapter_tags_by_uid(filepath: Path) -> dict[int, dict[str, str]]:
    """Return TTV=30 chapter tag blocks keyed by ChapterUID. Empty dict if none."""
    from festival_organizer.mkv_tags import extract_all_tags
    root = extract_all_tags(filepath)
    if root is None:
        return {}
    result: dict[int, dict[str, str]] = {}
    for tag in root.iter("Tag"):
        targets = tag.find("Targets")
        if targets is None:
            continue
        ttv = targets.find("TargetTypeValue")
        uid_el = targets.find("ChapterUID")
        if ttv is None or uid_el is None or int(ttv.text or "0") != 30:
            continue
        try:
            uid = int(uid_el.text or "0")
        except ValueError:
            continue
        block: dict[str, str] = {}
        for simple in tag.iter("Simple"):
            name_el = simple.find("Name")
            string_el = simple.find("String")
            if name_el is not None and string_el is not None and name_el.text:
                block[name_el.text] = string_el.text or ""
        if block:
            result[uid] = block
    return result


def write_chapter_mbid_tags(
    filepath: Path,
    merged_chapter_tags: dict[int, dict[str, str]],
) -> None:
    """Write merged TTV=30 chapter tags via mkv_tags.write_merged_tags.

    IMPORTANT: write_merged_tags replaces existing TTV=30 blocks wholesale
    when chapter_tags is provided. The `merged_chapter_tags` argument here
    must therefore already contain every tag that should remain on each
    chapter (PERFORMER, TITLE, LABEL, GENRE, etc.) plus the new
    MUSICBRAINZ_ARTISTIDS. Callers that pass only the MBID dict will wipe
    the file's existing per-chapter metadata.
    """
    from festival_organizer.mkv_tags import write_merged_tags
    write_merged_tags(filepath, new_tags={}, chapter_tags=merged_chapter_tags)


class ChapterArtistMbidsOperation(Operation):
    """Write per-chapter MUSICBRAINZ_ARTISTIDS based on CRATEDIGGER_TRACK_PERFORMER_NAMES.

    Runs in the enrich pipeline (wired by cli.py). Reads the file's existing
    chapter tags, resolves each unique CRATEDIGGER_TRACK_PERFORMER_NAMES
    entry via lookup_mbid (which consults ArtistMbidOverrides before the
    cache and network), and writes pipe-joined MBIDs with empty slots for
    misses so downstream consumers can zip SLUGS / NAMES / MBIDS by index.

    Existing per-chapter tags (CRATEDIGGER_TRACK_PERFORMER, TITLE,
    CRATEDIGGER_TRACK_LABEL, CRATEDIGGER_TRACK_GENRE,
    CRATEDIGGER_TRACK_PERFORMER_SLUGS, CRATEDIGGER_TRACK_PERFORMER_NAMES)
    are preserved; only MBIDs are added or updated.
    """
    name = "chapter_artist_mbids"
    display_name = "chapter_artist_mbids"

    def __init__(self, config=None, force: bool = False):
        self.config = config
        self.force = force
        self._cache = None
        self._overrides = None

    def _get_cache(self):
        if self._cache is None:
            from festival_organizer.fanart import MBIDCache
            ttl = 90
            if self.config is not None:
                ttl = self.config.cache_ttl.get("mbid_days", 90)
            self._cache = MBIDCache(ttl_days=ttl)
        return self._cache

    def _get_overrides(self):
        if self._overrides is None:
            from festival_organizer.fanart import ArtistMbidOverrides
            self._overrides = ArtistMbidOverrides()
        return self._overrides

    def is_needed(self, file_path: Path, media_file) -> bool:
        from festival_organizer.mkv_tags import MATROSKA_EXTS
        return file_path.suffix.lower() in MATROSKA_EXTS

    def execute(self, file_path: Path, media_file) -> OperationResult:
        from festival_organizer.fanart import compute_chapter_mbid_tags

        existing = _extract_chapter_tags_by_uid(file_path)
        if not existing:
            return OperationResult(self.name, "skipped", "no chapter tags")
        if not any("CRATEDIGGER_TRACK_PERFORMER_NAMES" in block for block in existing.values()):
            return OperationResult(
                self.name, "skipped",
                "no CRATEDIGGER_TRACK_PERFORMER_NAMES on any chapter (run identify)",
            )

        cache = self._get_cache()
        overrides = self._get_overrides()

        def resolver(name: str) -> str | None:
            return lookup_mbid(name, cache, overrides=overrides)

        new_mbid_tags = compute_chapter_mbid_tags(existing, resolver)
        if not new_mbid_tags:
            return OperationResult(self.name, "skipped", "no resolvable CRATEDIGGER_TRACK_PERFORMER_NAMES")

        # Short-circuit when every computed MBID matches what's already on disk.
        if not self.force:
            already_current = all(
                existing.get(uid, {}).get("MUSICBRAINZ_ARTISTIDS")
                == entry["MUSICBRAINZ_ARTISTIDS"]
                for uid, entry in new_mbid_tags.items()
            )
            if already_current:
                return OperationResult(self.name, "skipped", "MBIDs already current")

        # Merge new MBIDs INTO a copy of the existing chapter blocks so
        # write_merged_tags does not wipe PERFORMER / TITLE / etc.
        merged: dict[int, dict[str, str]] = {}
        for uid, block in existing.items():
            merged_block = dict(block)
            if uid in new_mbid_tags:
                merged_block["MUSICBRAINZ_ARTISTIDS"] = new_mbid_tags[uid]["MUSICBRAINZ_ARTISTIDS"]
            merged[uid] = merged_block

        write_chapter_mbid_tags(file_path, merged)
        return OperationResult(self.name, "done", f"wrote MBIDs for {len(new_mbid_tags)} chapters")


class AlbumArtistMbidsOperation(Operation):
    """Write album-level CRATEDIGGER_ALBUMARTIST_MBIDS from CRATEDIGGER_1001TL_ARTISTS.

    Mirrors ChapterArtistMbidsOperation but at TTV=70 (collection scope). Reads
    the file's CRATEDIGGER_1001TL_ARTISTS tag (written during identify),
    resolves each pipe-separated name via lookup_mbid, and writes an
    aligned pipe-joined MBID list with empty slots for misses so downstream
    consumers can zip SLUGS / ARTISTS / MBIDS by index.

    The shared ArtistMbidOverrides + MBIDCache mean a pin here also applies
    to per-chapter MUSICBRAINZ_ARTISTIDS (intended: MBIDs are properties of
    the artist, not of the tag context).
    """
    name = "album_artist_mbids"
    display_name = "album_artist_mbids"

    def __init__(self, config=None, force: bool = False):
        self.config = config
        self.force = force
        self._cache = None
        self._overrides = None

    def _get_cache(self):
        if self._cache is None:
            from festival_organizer.fanart import MBIDCache
            ttl = 90
            if self.config is not None:
                ttl = self.config.cache_ttl.get("mbid_days", 90)
            self._cache = MBIDCache(ttl_days=ttl)
        return self._cache

    def _get_overrides(self):
        if self._overrides is None:
            from festival_organizer.fanart import ArtistMbidOverrides
            self._overrides = ArtistMbidOverrides()
        return self._overrides

    def is_needed(self, file_path: Path, media_file) -> bool:
        from festival_organizer.mkv_tags import MATROSKA_EXTS
        return file_path.suffix.lower() in MATROSKA_EXTS

    def execute(self, file_path: Path, media_file) -> OperationResult:
        from festival_organizer.fanart import resolve_mbids_aligned
        from festival_organizer.mkv_tags import (
            _tag_values_from_root, extract_all_tags, write_merged_tags,
        )

        root = extract_all_tags(file_path)
        existing_70 = (_tag_values_from_root(root) if root is not None else {}).get(70, {})

        names_str = existing_70.get("CRATEDIGGER_1001TL_ARTISTS", "")
        if not names_str:
            return OperationResult(
                self.name, "skipped",
                "no CRATEDIGGER_1001TL_ARTISTS (run identify)",
            )

        names = [n for n in names_str.split("|") if n]
        if not names:
            return OperationResult(self.name, "skipped", "empty artists list")

        cache = self._get_cache()
        overrides = self._get_overrides()

        def resolver(name: str) -> str | None:
            return lookup_mbid(name, cache, overrides=overrides)

        mbids = resolve_mbids_aligned(names, resolver)
        if not any(mbids):
            return OperationResult(self.name, "skipped", "no resolvable artists")

        new_value = "|".join(mbids)

        if not self.force and existing_70.get("CRATEDIGGER_ALBUMARTIST_MBIDS", "") == new_value:
            return OperationResult(self.name, "skipped", "MBIDs already current")

        write_merged_tags(
            file_path,
            {70: {"CRATEDIGGER_ALBUMARTIST_MBIDS": new_value}},
            existing_root=root,
        )
        resolved_count = sum(1 for m in mbids if m)
        return OperationResult(
            self.name, "done",
            f"wrote MBIDs for {resolved_count}/{len(mbids)} artists",
        )
