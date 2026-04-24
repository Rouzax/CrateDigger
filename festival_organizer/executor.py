"""File executor: moves, copies, or renames files with collision handling."""
import logging
import shutil
from pathlib import Path

from festival_organizer.models import FileAction

logger = logging.getLogger(__name__)


def paths_are_same_file(a: Path, b: Path) -> bool:
    """True iff a and b refer to the same on-disk file.

    Correct on case-insensitive filesystems (NTFS, APFS default), where
    "Alok.mkv" and "ALOK.mkv" share one inode/file-id; samefile reports True.
    """
    try:
        return a.exists() and b.exists() and a.samefile(b)
    except OSError:
        return False


def resolve_collision(target: Path, source: Path | None = None) -> Path:
    """If target exists, append (1), (2), etc. until a free name is found.

    When source is provided and refers to the same on-disk file as target
    (case-only rename on a case-insensitive filesystem), the target is not a
    real collision; return it unchanged so the rename can proceed.
    """
    if not target.exists():
        return target
    if source is not None and paths_are_same_file(target, source):
        return target
    stem = target.stem
    ext = target.suffix
    parent = target.parent
    counter = 1
    while counter < 1000:
        candidate = parent / f"{stem} ({counter}){ext}"
        if not candidate.exists():
            return candidate
        counter += 1
    raise RuntimeError(f"Too many collisions for: {target}")


def execute_actions(actions: list[FileAction]) -> list[FileAction]:
    """Execute a list of file actions. Returns the same list with updated status.

    Never overwrites existing files — uses collision resolution.
    """
    for action in actions:
        try:
            # Skip if source and target are the same path
            if action.source.resolve() == action.target.resolve():
                action.status = "skipped"
                action.error = "Already at target location"
                continue

            # Resolve collisions
            final_target = resolve_collision(action.target)
            action.target = final_target

            # Create target directory
            final_target.parent.mkdir(parents=True, exist_ok=True)

            # Execute
            if action.action == "copy":
                shutil.copy2(str(action.source), str(final_target))
            else:
                # Both "move" and "rename" use shutil.move
                shutil.move(str(action.source), str(final_target))

            action.status = "done"

        except OSError as e:
            logger.warning(
                "File action failed (%s -> %s): %s",
                action.source, action.target, e,
            )
            action.status = "error"
            action.error = str(e)

    return actions
