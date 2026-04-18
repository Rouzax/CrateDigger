"""Pipeline runner: executes operations per file with live progress."""
from __future__ import annotations

import time
from pathlib import Path

from festival_organizer.models import MediaFile
from festival_organizer.operations import Operation, OperationResult
from festival_organizer.progress import ProgressPrinter, OrganizeContractProgress


def run_pipeline(
    files: list[tuple[Path, MediaFile, list[Operation]]],
    progress,
) -> list[list[OperationResult]]:
    """Run operations for each file, emitting live progress."""
    all_results = []
    is_contract = isinstance(progress, OrganizeContractProgress)

    for file_path, media_file, operations in files:
        # Determine target folder for display (legacy progress)
        target_folder = ""
        for op in operations:
            if op.name == "organize" and hasattr(op, "target"):
                target_folder = str(op.target.parent.name) + "/" + op.target.name
                break

        progress.file_start(file_path, target_folder)

        file_results = []
        current_path = file_path
        file_start_time = time.perf_counter()

        for op in operations:
            op_display = getattr(op, "display_name", "") or ""
            try:
                needed = op.is_needed(current_path, media_file)
            except Exception as e:
                file_results.append(OperationResult(op.name, "error", str(e), display_name=op_display))
                continue

            if needed:
                result = op.execute(current_path, media_file)
                result.display_name = op_display
                if op.name == "organize" and result.status == "done":
                    current_path = op.target
            else:
                result = OperationResult(op.name, "skipped", "exists", display_name=op_display)
            file_results.append(result)

        elapsed = time.perf_counter() - file_start_time

        if is_contract:
            # Find the organize operation and its result
            organize_op = None
            organize_result = None
            for op, r in zip(operations, file_results):
                if op.name == "organize":
                    organize_op = op
                    organize_result = r
                    break
            if organize_op and organize_result:
                progress.file_done(
                    source=file_path, media_file=media_file,
                    op=organize_op, result=organize_result,
                    elapsed_s=elapsed,
                )
        else:
            progress.file_done(file_results)

        progress.record_results(file_results)
        all_results.append(file_results)

    return all_results
