"""File executor: moves, copies, or renames files with collision handling."""
import shutil
from pathlib import Path

from festival_organizer.models import FileAction


def resolve_collision(target: Path) -> Path:
    """If target exists, append (1), (2), etc. until a free name is found."""
    if not target.exists():
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
            action.status = "error"
            action.error = str(e)

    return actions
