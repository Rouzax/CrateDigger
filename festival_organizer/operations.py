"""Composable operations with gap detection."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from festival_organizer.config import Config
from festival_organizer.models import MediaFile


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

    def __init__(self, config: Config, force: bool = False):
        self.config = config
        self.force = force

    def is_needed(self, file_path: Path, media_file: MediaFile) -> bool:
        folder_jpg = file_path.parent / "folder.jpg"
        if self.force:
            return True
        return not folder_jpg.exists()

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
            date_or_year = mf.date or mf.year or ""

            # Collect existing thumbs in folder for color extraction
            thumb_paths = list(file_path.parent.glob("*-thumb.jpg"))

            generate_album_poster(
                output_path=folder_jpg,
                festival=festival_display or mf.artist or "Unknown",
                date_or_year=date_or_year,
                detail=mf.stage or mf.location or "",
                thumb_paths=thumb_paths if thumb_paths else None,
            )
            return OperationResult(self.name, "done")
        except (OSError, ValueError) as e:
            return OperationResult(self.name, "error", str(e))


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
