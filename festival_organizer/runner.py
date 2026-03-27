"""Pipeline runner: executes operations per file with live progress."""
from __future__ import annotations

from pathlib import Path

from festival_organizer.models import MediaFile
from festival_organizer.operations import Operation, OperationResult
from festival_organizer.progress import ProgressPrinter


def run_pipeline(
    files: list[tuple[Path, MediaFile, list[Operation]]],
    progress: ProgressPrinter,
) -> list[list[OperationResult]]:
    """Run operations for each file, emitting live progress.

    Args:
        files: List of (file_path, media_file, operations) tuples.
            file_path is the current location of the file.
            Operations are executed in order.
        progress: ProgressPrinter for live output.

    Returns:
        List of result lists, one per file.
    """
    all_results = []

    for file_path, media_file, operations in files:
        # Determine target folder for display
        target_folder = ""
        for op in operations:
            if op.name == "organize" and hasattr(op, "target"):
                target_folder = str(op.target.parent.name) + "/"
                break

        progress.file_start(file_path, target_folder)

        file_results = []
        current_path = file_path

        for op in operations:
            try:
                needed = op.is_needed(current_path, media_file)
            except Exception as e:
                file_results.append(OperationResult(op.name, "error", str(e)))
                continue

            if needed:
                result = op.execute(current_path, media_file)
                # If organize succeeded, update path for downstream ops
                if op.name == "organize" and result.status == "done":
                    current_path = op.target
            else:
                result = OperationResult(op.name, "skipped", "exists")
            file_results.append(result)

        progress.file_done(file_results)
        progress.record_results(file_results)
        all_results.append(file_results)

    return all_results
