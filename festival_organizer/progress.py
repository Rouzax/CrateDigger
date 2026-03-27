"""Live progress output formatting."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from festival_organizer.operations import OperationResult


class ProgressPrinter:
    """Formats and prints live progress during pipeline execution."""

    def __init__(
        self,
        total: int,
        stream=None,
        quiet: bool = False,
        verbose: bool = False,
    ):
        self.total = total
        self.stream = stream or sys.stdout
        self.quiet = quiet
        self.verbose = verbose
        self._file_index = 0
        self._counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def print_header(
        self,
        command: str,
        source: Path,
        output: Path,
        layout: str,
        tools: list[str],
    ) -> None:
        """Print the run header."""
        w = self.stream.write
        w(f"CrateDigger — {command}\n")
        w("=" * 56 + "\n")
        w(f"Source:  {source}\n")
        w(f"Output:  {output}\n")
        w(f"Layout:  {layout}\n")
        if tools:
            w(f"Tools:   {', '.join(tools)}\n")
        else:
            w("Tools:   NONE (filename parsing only)\n")
        w("=" * 56 + "\n\n")

    def file_start(self, filename: Path, target_folder: str) -> None:
        """Print the start of processing a file."""
        self._file_index += 1
        if self.quiet:
            return
        w = self.stream.write
        w(f"\n [{self._file_index}/{self.total}] {filename.name}\n")
        if target_folder:
            w(f"        -> {target_folder}\n")

    def file_done(self, results: list[OperationResult]) -> None:
        """Print operation results for the current file."""
        if self.quiet:
            return
        parts = []
        for r in results:
            if r.status == "done":
                parts.append(f"v {r.name}")
            elif r.status == "skipped":
                detail = f" ({r.detail})" if r.detail else ""
                parts.append(f"skip {r.name}{detail}")
            elif r.status == "error":
                detail = f" ({r.detail})" if r.detail else ""
                parts.append(f"! {r.name}{detail}")
        if parts:
            self.stream.write(f"        {'  '.join(parts)}\n")

    def record_results(self, results: list[OperationResult]) -> None:
        """Record results for summary aggregation."""
        for r in results:
            self._counts[r.name][r.status] += 1

    def print_summary(self, log_path: Path | None = None) -> None:
        """Print the final summary."""
        w = self.stream.write
        w("\n" + "=" * 56 + "\n")
        parts = []
        for op_name, statuses in sorted(self._counts.items()):
            done = statuses.get("done", 0)
            label = op_name.upper()
            parts.append(f"{label}: {done}")
        w(" | ".join(parts) + "\n")
        if log_path:
            w(f"Log:  {log_path}\n")
        w("=" * 56 + "\n")
