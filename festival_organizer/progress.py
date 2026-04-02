"""Live progress output formatting."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.text import Text

from festival_organizer.console import escape, header_panel, make_console, status_text, summary_panel
from festival_organizer.operations import OperationResult


class ProgressPrinter:
    """Formats and prints live progress during pipeline execution."""

    def __init__(
        self,
        total: int,
        console: Console | None = None,
        quiet: bool = False,
        verbose: bool = False,
    ):
        self.total = total
        self.console = console or make_console()
        self.quiet = quiet
        self.verbose = verbose
        self._file_index = 0
        self._counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def print_header(
        self,
        command: str,
        rows: dict[str, str],
        missing_tools: list[str] | None = None,
    ) -> None:
        """Print the run header with command-specific rows."""
        self.console.print(header_panel(f"CrateDigger: {command}", rows))
        if missing_tools:
            for tool in missing_tools:
                self.console.print(f"  [yellow]Warning: {tool} not found (some features may be limited)[/yellow]")

    def file_start(self, filename: Path, target_folder: str) -> None:
        """Print the start of processing a file."""
        self._file_index += 1
        if self.quiet:
            return
        text = Text()
        text.append(f"\n[{self._file_index}/{self.total}] ", style="bold")
        text.append(filename.name)
        self.console.print(text)
        if target_folder:
            self.console.print(f"        -> {escape(target_folder)}")

    def file_done(self, results: list[OperationResult]) -> None:
        """Print operation results for the current file."""
        if self.quiet:
            return
        parts: list[Text] = []
        for r in results:
            parts.append(status_text(r.status, r.name, r.detail or ""))
        if parts:
            line = Text("        ")
            for i, part in enumerate(parts):
                if i > 0:
                    line.append("  ")
                line.append_text(part)
            self.console.print(line)

    def record_results(self, results: list[OperationResult]) -> None:
        """Record results for summary aggregation."""
        for r in results:
            self._counts[r.name][r.status] += 1

    def print_summary(self, log_path: Path | None = None) -> None:
        """Print the final summary."""
        counts = dict(self._counts)
        # Merge poster + album_poster into a combined "posters" entry
        if "poster" in counts or "album_poster" in counts:
            merged: dict[str, int] = defaultdict(int)
            for key in ("poster", "album_poster"):
                for status, count in counts.pop(key, {}).items():
                    merged[status] += count
            counts["posters"] = dict(merged)
        self.console.print(summary_panel(counts, log_path=log_path))
