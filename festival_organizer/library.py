"""Library root detection and marker management.

Logging:
    Logger: 'festival_organizer.library'
    Key events:
        - cleanup.permission_error (WARNING): Cannot remove directory due to permissions
        - cleanup.os_error (WARNING): OS error during directory cleanup
        - cleanup.unknown_hidden (WARNING): Directory kept because of unknown hidden files
        - cleanup.not_empty (DEBUG): Directory not removed because it still has entries
        - cleanup.removed (DEBUG): Empty directory removed
    See docs/logging.md for full guidelines.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_DIR = ".cratedigger"

# Files that are considered junk and can be deleted during cleanup.
JUNK_FILES = frozenset({
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
})

# Folder-level sidecar files that belong to the folder, not individual media.
# These are removed when no media files remain in the directory.
FOLDER_SIDECARS = frozenset({
    "folder.jpg",
    "folder.png",
    "fanart.jpg",
})


def find_library_root(start_path: Path) -> Path | None:
    """Walk up from start_path looking for .cratedigger/ marker.

    Returns the directory containing the marker, or None if not found.
    Stops at filesystem root to avoid infinite loops.
    """
    current = start_path.resolve()
    while True:
        if (current / MARKER_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def resolve_library_root(
    source: Path, output: Path | None = None
) -> Path | None:
    """Find the library root, checking output first, then source.

    When an explicit output path is given, its library root takes priority
    over any library root found from the source path.  This ensures that
    ``cratedigger organize <source> -o <library>`` picks up the config and
    assets stored in the output library.
    """
    output_root = find_library_root(output) if output is not None else None
    source_root = find_library_root(source)
    return output_root or source_root


def init_library(root: Path, layout: str | None = None) -> Path:
    """Initialize a library at root by creating .cratedigger/ marker.

    If .cratedigger/config.json already exists, merges layout setting
    without overwriting existing user settings.

    Returns path to the .cratedigger/ directory.
    """
    marker = root / MARKER_DIR
    marker.mkdir(exist_ok=True)

    config_path = marker / "config.json"
    if config_path.exists():
        existing = json.loads(config_path.read_text(encoding="utf-8"))
        if layout and "default_layout" not in existing:
            existing["default_layout"] = layout
            config_path.write_text(
                json.dumps(existing, indent=2) + "\n", encoding="utf-8"
            )
    else:
        config = {}
        if layout:
            config["default_layout"] = layout
        config_path.write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

    return marker


def cleanup_empty_dirs(root: Path) -> None:
    """Remove empty directories under *root* after an organize/move operation.

    Walks the tree bottom-up so that nested empty directories collapse correctly.

    Rules:
    - The *root* directory itself is never removed.
    - ``.cratedigger`` directories (and their ancestors up to *root*) are never removed.
    - Known junk files (.DS_Store, Thumbs.db, desktop.ini) are deleted before
      the empty check.  Unknown hidden files cause the directory to be kept
      (with a WARNING logged).
    - Orphaned folder-level sidecars (folder.jpg, fanart.jpg, etc.) are removed
      when no media files remain in the directory.
    - Permission errors are caught per-directory, logged as WARNING, and do not
      abort the cleanup of other directories.
    """
    root = root.resolve()

    for dirpath_str, dirnames, filenames in os.walk(str(root), topdown=False):
        dirpath = Path(dirpath_str)

        # Never touch root itself.
        if dirpath == root:
            continue

        # Never touch .cratedigger dirs or dirs containing one.
        if dirpath.name == MARKER_DIR:
            continue
        if (dirpath / MARKER_DIR).is_dir():
            continue

        try:
            _try_cleanup_dir(dirpath)
        except PermissionError as exc:
            logger.warning("Cannot clean up %s: %s", dirpath, exc)
        except OSError as exc:
            logger.warning("Error cleaning up %s: %s", dirpath, exc)


def _try_cleanup_dir(dirpath: Path) -> None:
    """Attempt to clean up a single directory.  Raises on permission errors."""
    entries = list(dirpath.iterdir())
    entry_names = {e.name for e in entries}

    # --- Phase 1: remove known junk files ---
    junk_in_dir = entry_names & JUNK_FILES
    for name in junk_in_dir:
        (dirpath / name).unlink()
    entries = [e for e in entries if e.name not in junk_in_dir]
    entry_names -= junk_in_dir

    # --- Phase 2: check for unknown hidden files ---
    unknown_hidden = [
        e.name for e in entries
        if e.name.startswith(".") and e.is_file()
    ]
    if unknown_hidden:
        logger.warning(
            "Keeping %s: contains unknown hidden file(s): %s",
            dirpath,
            ", ".join(sorted(unknown_hidden)),
        )
        return

    # --- Phase 3: remove orphaned folder-level sidecars (no media present) ---
    sidecar_names = entry_names & FOLDER_SIDECARS
    non_sidecar_entries = [e for e in entries if e.name not in sidecar_names]

    # If the only remaining entries are sidecars (no real files, no subdirs), remove them.
    if sidecar_names and not non_sidecar_entries:
        for name in sidecar_names:
            (dirpath / name).unlink()
        entries = []
        entry_names = set()
    else:
        entries = non_sidecar_entries
        entry_names -= sidecar_names

    # --- Phase 4: final empty check ---
    # Re-read to account for sub-dirs that may have been removed in earlier iterations.
    remaining = list(dirpath.iterdir())
    if remaining:
        remaining_names = [e.name for e in remaining]
        logger.debug(
            "Not removing %s: still contains %s",
            dirpath,
            ", ".join(sorted(remaining_names)),
        )
        return

    # Directory is truly empty — remove it.
    dirpath.rmdir()
    logger.debug("Removed empty directory: %s", dirpath)
