"""Composable operations with gap detection."""

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
from festival_organizer.cache_maintenance import cache_dj_artwork
from festival_organizer.cache_ttl import hashed_jitter_factor
from festival_organizer.config import Config
from festival_organizer.fanart import lookup_mbid
from festival_organizer.models import MediaFile
from festival_organizer.paths import same_library_path

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

    def __init__(
        self, target: Path, action: str = "move", output_root: Path | None = None
    ):
        self.target = target
        self.action = action  # "move", "copy", "rename"
        self.output_root = output_root
        self.sidecars_moved = 0

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        # When output_root is available, use same_library_path so the
        # prefix (drive letter on Windows) is compared case-insensitively
        # while the library-relative portion stays case-sensitive for
        # canonical-casing renames like Alok -> ALOK.
        if self.output_root is not None:
            needed = not same_library_path(file_path, self.target, self.output_root)
            try:
                src_rel = str(file_path.relative_to(self.output_root))
            except ValueError:
                src_rel = str(file_path)
            try:
                tgt_rel = str(self.target.relative_to(self.output_root))
            except ValueError:
                tgt_rel = str(self.target)
            logger.debug(
                "organize.is_needed: source=%s target=%s needed=%s",
                src_rel,
                tgt_rel,
                needed,
            )
            return needed
        needed = str(file_path) != str(self.target)
        logger.debug(
            "organize.is_needed: source=%s target=%s needed=%s",
            file_path.name,
            self.target.name,
            needed,
        )
        return needed

    # Folder-level files that belong to the folder, not individual videos.
    FOLDER_LEVEL_FILES = frozenset({"folder.jpg", "fanart.jpg"})

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.executor import resolve_collision

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
            logger.debug(
                "organize.action: file=%s action=%s target=%s",
                file_path.name,
                self.action,
                target.name,
            )
            # Update target so downstream operations (nfo, art, etc.) use the
            # resolved path. This mutation is read by run_pipeline(); requires
            # serial execution; do not reuse operation instances across files.
            self.target = target

            # Move sidecar files that share the video's stem
            new_stem = target.stem
            self.sidecars_moved = self._move_sidecars(
                old_dir,
                old_stem,
                target.parent,
                new_stem,
                shutil,
                self.action,
            )

            return OperationResult(self.name, "done")
        except OSError as e:
            return OperationResult(self.name, "error", str(e))

    def _move_sidecars(
        self,
        old_dir: Path,
        old_stem: str,
        new_dir: Path,
        new_stem: str,
        shutil,
        action: str,
    ) -> int:
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
            suffix = sidecar.name[len(old_stem) :]  # e.g. ".nfo" or "-poster.jpg"
            new_name = new_stem + suffix
            new_path = new_dir / new_name

            try:
                if action == "copy":
                    shutil.copy2(sidecar, new_path)
                elif action == "rename":
                    sidecar.rename(new_path)
                else:
                    shutil.move(str(sidecar), str(new_path))
                logger.debug(
                    "organize.sidecar: action=%s source=%s target=%s",
                    action,
                    sidecar.name,
                    new_path.name,
                )
                moved += 1
            except OSError as e:
                logger.warning(
                    'organize.sidecar: status=failed action=%s file=%s error="%s"',
                    action,
                    sidecar.name,
                    e,
                )
        return moved


class NfoOperation(Operation):
    name = "nfo"

    def __init__(
        self, config: Config, force: bool = False, dj_cache: object | None = None
    ):
        self.config = config
        self.force = force
        self.dj_cache = dj_cache

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        nfo_path = file_path.with_suffix(".nfo")
        if not nfo_path.exists():
            return True
        return self._content_changed(nfo_path, file_path, media_file)

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.nfo import generate_nfo

        try:
            dateadded = self._read_dateadded(file_path.with_suffix(".nfo"))
            generate_nfo(
                media_file,
                file_path,
                self.config,
                dj_cache=self.dj_cache,
                dateadded=dateadded,
            )
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))

    def _content_changed(
        self, nfo_path: Path, file_path: Path, media_file: MediaFile
    ) -> bool:
        from festival_organizer.nfo import generate_nfo_xml

        try:
            existing = nfo_path.read_text(encoding="utf-8")
        except OSError:
            return True
        dateadded = _extract_dateadded(existing)
        expected = generate_nfo_xml(
            media_file,
            file_path,
            self.config,
            dj_cache=self.dj_cache,
            dateadded=dateadded,
        )
        if existing.strip() != expected.strip():
            logger.info("nfo.stale: file=%s reason=content_changed", file_path.name)
            return True
        return False

    @staticmethod
    def _read_dateadded(nfo_path: Path) -> str | None:
        try:
            return _extract_dateadded(nfo_path.read_text(encoding="utf-8"))
        except OSError:
            return None


def _extract_dateadded(nfo_text: str) -> str | None:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(nfo_text)
        elem = root.find("dateadded")
        return elem.text if elem is not None else None
    except ET.ParseError:
        return None


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


def _resolve_poster_fields(media_file: MediaFile, config: Config) -> dict[str, str]:
    """Resolve the exact fields passed to generate_set_poster (shared by poster + cover ops)."""
    mf = media_file
    festival_slot = mf.place
    if mf.edition:
        festival_slot = config.get_place_display(mf.place, mf.edition)
    venue_used_in_slot = mf.place_kind in ("venue", "location")
    venue = "" if venue_used_in_slot else (mf.venue or "")
    return {
        "artist": mf.display_artist or mf.artist or "Unknown",
        "festival": festival_slot or "",
        "date": mf.date or "",
        "year": mf.year or "",
        "stage": mf.stage or "",
        "venue": venue,
    }


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
        if not poster.exists():
            return True
        from festival_organizer.poster import build_cover_stamp, read_poster_stamp

        current = build_cover_stamp(
            **_resolve_poster_fields(media_file, self.config),
            artists_1001tl=media_file.artists_1001tl,
        )
        return read_poster_stamp(poster) != current

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.poster import generate_set_poster

        try:
            thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
            poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
            f = _resolve_poster_fields(media_file, self.config)
            generate_set_poster(
                source_image_path=thumb,
                output_path=poster,
                artist=f["artist"],
                festival=f["festival"],
                date=f["date"],
                year=f["year"],
                detail=f["stage"],
                venue=f["venue"],
                artists_1001tl=media_file.artists_1001tl,
            )
            # Matroska files are stamped by CoverEmbedOperation after the embed (the
            # stamp means "embed is current"). Non-Matroska files have no embed step,
            # so stamp the sidecar here to enable the same content-aware regeneration.
            from festival_organizer.mkv_tags import MATROSKA_EXTS

            if file_path.suffix.lower() not in MATROSKA_EXTS:
                from festival_organizer.poster import (
                    build_cover_stamp,
                    inject_poster_stamp,
                )

                inject_poster_stamp(
                    poster,
                    build_cover_stamp(**f, artists_1001tl=media_file.artists_1001tl),
                )
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))


class CoverEmbedOperation(Operation):
    name = "cover"
    display_name = "cover"

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        from festival_organizer.mkv_tags import MATROSKA_EXTS

        if file_path.suffix.lower() not in MATROSKA_EXTS:
            return False
        poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
        if not poster.exists():
            return False  # nothing to embed
        if self.force:
            return True
        from festival_organizer.poster import build_cover_stamp, read_poster_stamp

        current = build_cover_stamp(
            **_resolve_poster_fields(media_file, self.config),
            artists_1001tl=media_file.artists_1001tl,
        )
        # The stamp is written only after a successful embed, so a match means the
        # embedded cover is already current. Mismatch/absent -> (re-)embed.
        # The sidecar stamp is a proxy for the MKV embed being current (they are
        # separate files); use --force to re-embed if the embedded cover is altered
        # outside CrateDigger.
        return read_poster_stamp(poster) != current

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer import cover_embed
        from festival_organizer.mkv_attachments import image_ratio_class
        from festival_organizer.poster import build_cover_stamp, inject_poster_stamp

        poster = file_path.with_name(f"{file_path.stem}-poster.jpg")
        thumb = file_path.with_name(f"{file_path.stem}-thumb.jpg")
        try:
            if image_ratio_class(poster) != "portrait":
                logger.warning(
                    "cover.skip: file=%s reason=poster_not_portrait", file_path.name
                )
                return OperationResult(self.name, "error", "poster not portrait")
            if not cover_embed.converge_cover_attachments(file_path, poster, thumb):
                return OperationResult(self.name, "error", "cover convergence failed")
            # Stamp the sidecar only after a successful embed.
            stamp = build_cover_stamp(
                **_resolve_poster_fields(media_file, self.config),
                artists_1001tl=media_file.artists_1001tl,
            )
            inject_poster_stamp(poster, stamp)
            return OperationResult(self.name, "done")
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            return OperationResult(self.name, "error", str(e))


class AlbumPosterOperation(Operation):
    name = "posters"
    display_name = "album_poster"

    def __init__(
        self,
        config: Config,
        force: bool = False,
        library_root: Path | None = None,
        ttl_days: int = 90,
    ):
        self.config = config
        self.force = force
        self.library_root = library_root
        self._ttl_days = ttl_days
        self._completed_folders: set[Path] = set()
        self._logo_hits: dict[str, Path] = {}  # place -> logo path
        self._logo_misses: set[str] = set()  # places without curated logo

    @property
    def generated_folders(self) -> set[Path]:
        """Folders whose folder.jpg this op generated or refreshed this run.

        With per-level generation a single file touches several levels (place,
        year, artist); the Kodi sync uses this to clear textures for all of them,
        not just the file's own folder.
        """
        return self._completed_folders

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        from festival_organizer.poster import read_poster_stamp

        for folder, ptype, parent in self._layout_levels(file_path, media_file):
            if folder in self._completed_folders:
                continue
            if self.force:
                return True
            folder_jpg = folder / "folder.jpg"
            if not folder_jpg.exists():
                return True
            # Regenerate when the embedded stamp no longer matches what we would
            # render at this level (type/name/year/edition or version changed).
            if read_poster_stamp(folder_jpg) != self._level_stamp(
                folder, ptype, parent, media_file
            ):
                return True
        return False

    def _consensus_year(self, folder: Path) -> str:
        """Single year shared by all videos in a folder's subtree, or '' if mixed/none.

        Scans the subtree (not just direct children) so a year folder whose videos
        live one or more levels deeper (e.g. place_nested Place/Year/Artist) still
        resolves its year for the badge and the stamp.
        """
        from festival_organizer.parsers import parse_filename

        years: set[str] = set()
        for video in folder.rglob("*"):
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                yr = parse_filename(video, self.config).get("year", "")
                if yr:
                    years.add(yr)
        return years.pop() if len(years) == 1 else ""

    def _layout_levels(
        self, file_path: Path, mf: MediaFile
    ) -> list[tuple[Path, str, str | None]]:
        """Folder levels to render for this file: (folder, poster_type, parent_type).

        The file sits at ``<library>/<seg0>/.../<segN-1>/file``, so the last
        ``len(segments)`` folders map one-to-one to the layout segments and are typed
        accordingly. ``parent_type`` is the type of the segment above (None at the
        top), used to name and color year folders by their parent (place or artist).
        """
        segments = self._get_layout_segments(mf.content_type)
        if not segments:
            return [(file_path.parent, self._get_folder_poster_type(mf), None)]

        # The file sits at <library>/<seg0>/.../<segN-1>/file, so the last
        # len(segments) folders map 1:1 to the layout's segments. Bound the walk to
        # that depth instead of walking up to a .cratedigger marker (which can live
        # far above an un-marked library), so posters are never written above the
        # library and the result does not depend on marker placement.
        ancestors: list[Path] = []
        folder = file_path.parent
        for _ in range(len(segments)):
            ancestors.append(folder)
            if folder.parent == folder:
                break
            folder = folder.parent
        ancestors.reverse()  # shallowest -> deepest, aligned with the segment tail
        seg_tail = segments[-len(ancestors) :]

        def _typed(seg: str) -> str:
            return "artist" if seg == "festival" and mf.place_kind == "artist" else seg

        levels: list[tuple[Path, str, str | None]] = []
        for i, fdr in enumerate(ancestors):
            parent = _typed(seg_tail[i - 1]) if i else None
            levels.append((fdr, _typed(seg_tail[i]), parent))
        return levels

    def _level_stamp_fields(
        self, ptype: str, parent: str | None, year: str, mf: MediaFile
    ) -> dict:
        """Identity fields for a folder-poster stamp at a given level."""
        if ptype == "artist":
            return {
                "poster_type": "artist",
                "name": mf.artist or "",
                "year": "",
                "edition": "",
            }
        if ptype == "year":
            parent_is_place = parent == "festival"
            return {
                "poster_type": "year",
                "name": (mf.place if parent_is_place else mf.artist) or "",
                "year": year or "",
                "edition": (mf.edition or "") if parent_is_place else "",
            }
        return {
            "poster_type": ptype,
            "name": mf.place or "",
            "year": "",
            "edition": mf.edition or "",
        }

    def _level_stamp(
        self, folder: Path, ptype: str, parent: str | None, mf: MediaFile
    ) -> bytes:
        from festival_organizer.poster import build_folder_stamp

        year = self._consensus_year(folder) if ptype == "year" else ""
        return build_folder_stamp(
            **self._level_stamp_fields(ptype, parent, year, mf),
            bg=self._expected_bg_fingerprint(ptype, mf),
        )

    def _expected_bg_fingerprint(self, ptype: str, mf: MediaFile) -> str:
        """Cheap, network-free fingerprint of the background image the poster uses.

        Lets the stamp change (so the poster regenerates) when the underlying
        artwork changes, e.g. refreshed DJ artwork for an artist folder or a swapped
        curated logo for a place. Computed from the known cache/logo path with a
        couple of stat()s, no download and no ffprobe. Year folders render a gradient
        with no background image, so they have no fingerprint.
        """
        path: Path | None = None
        if ptype == "festival":
            path = self._find_curated_logo(mf.place, mf.edition)
        elif ptype == "artist" and mf.artist:
            slug = mf.artist_slugs[0] if mf.artist_slugs else None
            key = paths.artist_cache_folder_key(
                mf.artist, slug=slug, dj_cache=self.config.dj_cache
            )
            artist_dir = paths.artist_cache_dir(key)
            for name in ("dj-artwork.jpg", "fanart.jpg"):
                cand = artist_dir / name
                if cand.exists():
                    path = cand
                    break
        if path and path.exists():
            st = path.stat()
            return f"{path.name}:{int(st.st_mtime)}:{st.st_size}"
        return ""

    def _expected_folder_stamp(self, mf: MediaFile, folder: Path) -> bytes:
        """Single-folder convenience (no library_root / tests): stamp for this folder."""
        return self._level_stamp(folder, self._get_folder_poster_type(mf), None, mf)

    def _get_folder_poster_type(self, mf: MediaFile) -> str:
        """Determine poster type from the first segment of the layout template.

        Priority for mixed segments: {place} > {artist} > {year}.
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

    @staticmethod
    def _classify_segment(segment: str) -> str:
        """Classify a template segment by priority: place > artist > year."""
        if "{place}" in segment:
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
        from festival_organizer.normalization import normalise_name
        from festival_organizer.parsers import parse_filename

        artists_in_folder: set[str] = set()
        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                parsed = parse_filename(video, self.config)
                if parsed.get("artist"):
                    artists_in_folder.add(normalise_name(parsed["artist"]).lower())
                if len(artists_in_folder) > 1:
                    logger.info(
                        "enrich.album_poster: artists_in_folder=%d style=festival",
                        len(artists_in_folder),
                    )
                    return None  # Multi-artist folder, skip fanart background

        # Single artist (or couldn't determine); look for their fanart
        key = paths.artist_cache_folder_key(artist, dj_cache=self.config.dj_cache)
        candidate = paths.artist_cache_dir(key) / "fanart.jpg"
        result = candidate if candidate.exists() else None
        logger.info(
            "enrich.album_poster: artists_in_folder=1 style=%s",
            "artist" if result else "festival",
        )
        return result

    def _download_artwork(
        self, url: str, cache_subdir: str, max_width: int | None = None
    ) -> Path | None:
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
            logger.debug(
                "enrich.artwork_cache: status=stale age_days=%d ttl=%.1f file=%s",
                int(age_days),
                effective_ttl,
                cached.name,
            )
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
                        img = img.resize(new_size, Image.Resampling.LANCZOS)
                        img.save(cached)
            logger.info(
                "enrich.artwork_download: status=ok url=%s target=%s", url, cached.name
            )
            return cached
        except (requests.RequestException, OSError) as e:
            logger.debug('enrich.artwork_download: status=failed error="%s"', e)
            return None

    def _download_dj_artwork(
        self, url: str, artist: str, slug: str | None = None
    ) -> Path | None:
        """Download DJ artwork, convert to JPEG, crop/resize, save to artist dir.

        Resolves the canonical artist cache key, then delegates the
        download/crop/resize/TTL work to :func:`cache_dj_artwork` (shared with the
        dj_cache-driven warm step), routing log events through this module's logger
        so per-file enrich output is unchanged.
        """
        if not url or not artist:
            return None
        key = paths.artist_cache_folder_key(
            artist, slug=slug, dj_cache=self.config.dj_cache
        )
        cached = paths.artist_cache_dir(key) / "dj-artwork.jpg"
        return cache_dj_artwork(
            url, cached, self._ttl_days, artist_label=artist, log=logger
        )

    def _find_curated_logo(self, place: str, edition: str = "") -> Path | None:
        """Find curated logo for a place from library or user-level folders.

        Library lookup checks ``.cratedigger/places/<name>/`` first, then the
        user-global :func:`paths.places_logo_dir`. Tries edition-specific path
        first (e.g. ``places/EDC Las Vegas/logo.png``), then falls back to the
        canonical name (e.g. ``places/EDC/logo.png``).
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
            search_dirs: list[Path] = []
            if self.library_root:
                search_dirs.append(self.library_root / ".cratedigger" / "places" / name)
            search_dirs.append(paths.places_logo_dir() / name)
            for d in search_dirs:
                for ext in ("jpg", "jpeg", "png", "webp"):
                    candidate = d / f"logo.{ext}"
                    if candidate.exists():
                        logger.info("enrich.curated_logo: path=%s", candidate)
                        return candidate
        return None

    def _find_dj_artwork(self, folder: Path) -> Path | None:
        """Find DJ artwork URL from media files in folder, download and cache."""
        from festival_organizer.analyzer import analyse_file

        for video in folder.iterdir():
            if video.suffix.lower() in (".mkv", ".mp4", ".webm"):
                mf = analyse_file(video, folder, self.config)
                logger.debug(
                    "enrich.dj_artwork: url=%s", mf.dj_artwork_url or "(empty)"
                )
                if mf.dj_artwork_url and mf.artist:
                    slug = mf.artist_slugs[0] if mf.artist_slugs else None
                    result = self._download_dj_artwork(
                        mf.dj_artwork_url, mf.artist, slug=slug
                    )
                    if result:
                        return result
                # Fallback: fetch DJ artwork from tracklist page
                if mf.tracklists_url and mf.artist:
                    result = self._fetch_dj_artwork_from_tracklist(
                        mf.tracklists_url, mf.artist
                    )
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
                    slug = mf.artist_slugs[0] if mf.artist_slugs else None
                    self._download_dj_artwork(mf.dj_artwork_url, mf.artist, slug=slug)

    def _fetch_dj_artwork_from_tracklist(
        self, tracklist_url: str, artist: str
    ) -> Path | None:
        """Fetch DJ artwork by scraping a 1001TL tracklist page for DJ slugs.

        Returns local cached path or None on failure.
        """
        try:
            email, password = self.config.tracklists_credentials
            if not email or not password:
                logger.debug(
                    "enrich.dj_artwork_fallback: status=skipped reason=no_credentials"
                )
                return None

            from festival_organizer.tracklists import canary
            from festival_organizer.tracklists.api import (
                TracklistSession,
                _extract_dj_slugs,
            )

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
                logger.debug(
                    "enrich.dj_artwork_fallback: status=skipped reason=no_slugs"
                )
                return None

            profile = api._fetch_dj_profile(slugs[0])
            dj_artwork_url = profile["artwork_url"]
            if not dj_artwork_url:
                logger.debug(
                    "enrich.dj_artwork_fallback: status=skipped reason=no_artwork slug=%s",
                    slugs[0],
                )
                return None

            return self._download_dj_artwork(dj_artwork_url, artist)
        except Exception as e:
            logger.debug('enrich.dj_artwork_fallback: status=failed error="%s"', e)
            return None

    def _resolve_background(
        self, priority: list[str], folder: Path, media_file: MediaFile
    ) -> tuple[Path | None, str]:
        """Walk the background priority chain, return first successful image and source name."""
        tried_curated = False
        for source in priority:
            bg = self._try_background_source(source, folder, media_file)
            if source == "curated_logo":
                tried_curated = True
                if bg and media_file.place:
                    display = self.config.get_place_display(
                        media_file.place, media_file.edition
                    )
                    self._logo_hits[display] = bg
            if bg:
                logger.info("enrich.album_poster: source=%s status=selected", source)
                return bg, source
            logger.debug("enrich.album_poster: source=%s status=unavailable", source)
        if tried_curated and media_file.place:
            display = self.config.get_place_display(
                media_file.place, media_file.edition
            )
            if display not in self._logo_hits:
                self._logo_misses.add(display)
        return None, ""

    def _try_background_source(
        self, source: str, folder: Path, media_file: MediaFile
    ) -> Path | None:
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
            return ps.get(
                "artist_background_priority", ["dj_artwork", "fanart_tv", "gradient"]
            )
        if poster_type == "festival":
            return ps.get("place_background_priority", ["curated_logo", "gradient"])
        return ps.get("year_background_priority", ["gradient"])

    def _place_brand_color(self, mf: MediaFile) -> tuple[int, int, int] | None:
        """Brand color for mf's place/edition from places.json, or None."""
        from festival_organizer.poster import _hex_to_rgb

        fc = self.config.place_config.get(mf.place, {})
        color_hex = fc.get("editions", {}).get(mf.edition, {}).get("color") or fc.get(
            "color"
        )
        return _hex_to_rgb(color_hex) if color_hex else None

    def _warm_backgrounds(self, video_folder: Path, mf: MediaFile) -> None:
        """Warm artwork caches once per run so every level can resolve its background."""
        self._try_background_source("curated_logo", video_folder, mf)
        self._try_background_source("fanart_tv", video_folder, mf)
        self._warm_dj_artwork_cache(video_folder)

    def _render_level(
        self,
        folder: Path,
        ptype: str,
        parent: str | None,
        video_folder: Path,
        mf: MediaFile,
    ) -> None:
        """Render and stamp the folder.jpg for one folder level."""
        from festival_organizer.poster import generate_album_poster, inject_poster_stamp

        folder_jpg = folder / "folder.jpg"
        date_or_year = self._consensus_year(folder)
        # Artwork/colour sources scan the video-bearing folder (the artist/place
        # identity is consistent up the tree for this file); thumbs come from the
        # subtree so an ancestor folder still gets a colour.
        thumb_paths = list(folder.rglob("*-thumb.jpg"))
        place_color = self._place_brand_color(mf)
        logger.debug(
            "enrich.album_poster: folder=%s type=%s parent=%s",
            folder.name,
            ptype,
            parent,
        )

        if ptype == "artist":
            priority = self._get_priority_chain_for_poster_type("artist")
            bg_path, bg_source = self._resolve_background(priority, video_folder, mf)
            generate_album_poster(
                output_path=folder_jpg,
                festival=mf.artist or "Unknown",
                date_or_year=date_or_year,
                detail=mf.stage or "",
                edition="",
                thumb_paths=thumb_paths or None,
                override_color=None,
                background_image_path=bg_path,
                background_source=bg_source,
                hero_text=mf.artist or "",
            )
        elif ptype == "year":
            parent_is_place = parent == "festival"
            name = (mf.place if parent_is_place else mf.artist) or "Unknown"
            generate_album_poster(
                output_path=folder_jpg,
                festival=name,
                date_or_year=date_or_year,
                detail="",
                edition=(mf.edition or "") if parent_is_place else "",
                thumb_paths=thumb_paths or None,
                override_color=place_color if parent_is_place else None,
                background_image_path=None,
                background_source="",
                hero_text=None,
                year_badge=date_or_year or mf.year,
            )
        else:  # festival / place
            priority = self._get_priority_chain_for_poster_type("festival")
            bg_path, bg_source = self._resolve_background(priority, video_folder, mf)
            generate_album_poster(
                output_path=folder_jpg,
                festival=mf.place or "Unknown",
                date_or_year=date_or_year,
                detail=mf.stage or "",
                edition=mf.edition or "",
                thumb_paths=thumb_paths or None,
                override_color=place_color,
                background_image_path=bg_path,
                background_source=bg_source,
                hero_text=None,
            )
        inject_poster_stamp(folder_jpg, self._level_stamp(folder, ptype, parent, mf))

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        try:
            mf = media_file
            video_folder = file_path.parent
            self._warm_backgrounds(video_folder, mf)
            for folder, ptype, parent in self._layout_levels(file_path, mf):
                if folder in self._completed_folders:
                    continue
                self._render_level(folder, ptype, parent, video_folder, mf)
                self._completed_folders.add(folder)
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
            logo_root = self.library_root / ".cratedigger" / "places"
            if logo_root.is_dir():
                for d in sorted(logo_root.iterdir()):
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

    def __init__(
        self,
        config: Config,
        library_root: Path,
        force: bool = False,
        ttl_days: int = 90,
        mbid_cache=None,
    ):
        self.config = config
        self.library_root = library_root
        self.force = force
        self._ttl_days = ttl_days
        self._completed_artists: set[str] = set()
        self._cache = mbid_cache

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

    def _artist_dir(self, key: str) -> Path:
        """Resolve per-artist cache directory from a folder key."""
        return paths.artist_cache_dir(key)

    def _artist_targets(self, media_file: MediaFile) -> list[tuple[str, str]]:
        """Return (display_name, folder_key) per artist to fetch fanart for.

        Prefers the 1001TL slug list; falls back to split_artists for files
        with no slug tag (non-1001TL).
        """
        from festival_organizer.fanart import split_artists

        if media_file.artist_slugs and len(media_file.artist_slugs) == len(
            media_file.artists
        ):
            return [
                (
                    name,
                    paths.artist_cache_folder_key(
                        name, slug=slug, dj_cache=self.config.dj_cache
                    ),
                )
                for name, slug in zip(
                    media_file.artists, media_file.artist_slugs, strict=True
                )
            ]
        return [
            (name, paths.artist_cache_folder_key(name, dj_cache=self.config.dj_cache))
            for name in split_artists(
                media_file.artist, groups=self.config.artist_groups
            )
        ]

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if not self.config.fanart_enabled or not self.config.fanart_project_api_key:
            return False
        if not media_file.artist:
            return False
        for name, key in self._artist_targets(media_file):
            if name in self._completed_artists:
                continue
            d = self._artist_dir(key)
            if self.force:
                return True
            if self._is_stale(d / "clearlogo.png") or self._is_stale(d / "fanart.jpg"):
                return True
        return False

    def execute(self, file_path: Path, media_file: MediaFile) -> OperationResult:
        from festival_organizer.fanart import (
            download_artist_images,
            fetch_artist_images,
            lookup_mbid,
            pick_best_background,
            pick_best_logo,
        )

        fetched = []
        for artist, key in self._artist_targets(media_file):
            if artist in self._completed_artists:
                continue
            d = self._artist_dir(key)
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
                        bg = pick_best_background(
                            fanart_data.get("artistbackground", [])
                        )
                        if bg and not media_file.fanart_url:
                            media_file.fanart_url = bg["url"]

                logo_ok, bg_ok = download_artist_images(
                    artist,
                    d,
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
            return OperationResult(
                self.name, "done", f"fetched for: {', '.join(fetched)}"
            )
        return OperationResult(self.name, "skipped", "already cached or not available")


class TagsOperation(Operation):
    name = "tags"

    def __init__(self, force: bool = False):
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        if self.force:
            return True
        from festival_organizer.mkv_tags import MATROSKA_EXTS

        # embed_tags compares desired vs existing tags and skips the write
        # when nothing changed, so Matroska files always return True here.
        return file_path.suffix.lower() in MATROSKA_EXTS

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
    chapter (CRATEDIGGER_TRACK_PERFORMER, CRATEDIGGER_TRACK_TITLE, etc.) plus the new
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

    Existing per-chapter tags (CRATEDIGGER_TRACK_PERFORMER, CRATEDIGGER_TRACK_TITLE,
    CRATEDIGGER_TRACK_LABEL, CRATEDIGGER_TRACK_GENRE,
    CRATEDIGGER_TRACK_PERFORMER_SLUGS, CRATEDIGGER_TRACK_PERFORMER_NAMES)
    are preserved; only MBIDs are added or updated.
    """

    name = "chapter_artist_mbids"
    display_name = "chapter_artist_mbids"

    def __init__(
        self, config=None, force: bool = False, mbid_cache=None, mbid_overrides=None
    ):
        self.config = config
        self.force = force
        self._cache = mbid_cache
        self._overrides = mbid_overrides

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
        if not any(
            "CRATEDIGGER_TRACK_PERFORMER_NAMES" in block for block in existing.values()
        ):
            return OperationResult(
                self.name,
                "skipped",
                "no CRATEDIGGER_TRACK_PERFORMER_NAMES on any chapter (run identify)",
            )

        cache = self._get_cache()
        overrides = self._get_overrides()

        def resolver(name: str) -> str | None:
            return lookup_mbid(name, cache, overrides=overrides)

        new_mbid_tags = compute_chapter_mbid_tags(existing, resolver)
        if not new_mbid_tags:
            return OperationResult(
                self.name, "skipped", "no resolvable CRATEDIGGER_TRACK_PERFORMER_NAMES"
            )

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
        # write_merged_tags does not wipe CRATEDIGGER_TRACK_PERFORMER / CRATEDIGGER_TRACK_TITLE / etc.
        merged: dict[int, dict[str, str]] = {}
        for uid, block in existing.items():
            merged_block = dict(block)
            if uid in new_mbid_tags:
                merged_block["MUSICBRAINZ_ARTISTIDS"] = new_mbid_tags[uid][
                    "MUSICBRAINZ_ARTISTIDS"
                ]
            merged[uid] = merged_block

        write_chapter_mbid_tags(file_path, merged)
        return OperationResult(
            self.name, "done", f"wrote MBIDs for {len(new_mbid_tags)} chapters"
        )


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

    def __init__(
        self, config=None, force: bool = False, mbid_cache=None, mbid_overrides=None
    ):
        self.config = config
        self.force = force
        self._cache = mbid_cache
        self._overrides = mbid_overrides

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
            _tag_values_from_root,
            extract_all_tags,
            write_merged_tags,
        )

        root = extract_all_tags(file_path)
        existing_70 = (_tag_values_from_root(root) if root is not None else {}).get(
            70, {}
        )

        names_str = existing_70.get("CRATEDIGGER_1001TL_ARTISTS", "")
        if not names_str:
            return OperationResult(
                self.name,
                "skipped",
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

        if (
            not self.force
            and existing_70.get("CRATEDIGGER_ALBUMARTIST_MBIDS", "") == new_value
        ):
            return OperationResult(self.name, "skipped", "MBIDs already current")

        write_merged_tags(
            file_path,
            {70: {"CRATEDIGGER_ALBUMARTIST_MBIDS": new_value}},
            existing_root=root,
        )
        resolved_count = sum(1 for m in mbids if m)
        return OperationResult(
            self.name,
            "done",
            f"wrote MBIDs for {resolved_count}/{len(mbids)} artists",
        )
