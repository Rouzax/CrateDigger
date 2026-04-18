"""Live progress output formatting."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.text import Text

from festival_organizer.console import (
    enrich_summary_panel,
    escape,
    header_panel,
    make_console,
    organize_summary_panel,
    status_text,
    summary_panel,
    verdict,
)
from festival_organizer.operations import OperationResult


_TRIVIAL_SKIP_REASONS = frozenset({"exists", ""})


def _enrich_badge(results: list[OperationResult]) -> str:
    """Compute a verdict badge from a list of enrich operation results.

    Worst-wins: error > done > up-to-date.
    """
    statuses = {r.status for r in results}
    if "error" in statuses:
        return "error"
    if "done" in statuses:
        return "done"
    return "up-to-date"


def _enrich_detail(results: list[OperationResult]) -> str:
    """Build a human-readable detail line from enrich operation results.

    Groups operations by outcome: done names are comma-joined, errors and
    non-trivial skips get explicit callouts separated by semicolons.
    """
    done_names: list[str] = []
    error_parts: list[str] = []
    notable_skips: list[str] = []

    for r in results:
        label = r.display_name or r.name
        if r.status == "done":
            done_names.append(label)
        elif r.status == "error":
            error_parts.append(f"{label} error: {r.detail}")
        elif r.status == "skipped" and r.detail not in _TRIVIAL_SKIP_REASONS:
            notable_skips.append(f"{label} skipped: {r.detail}")

    has_callouts = bool(error_parts) or bool(notable_skips)

    if not done_names and not has_callouts:
        return "all up to date"

    segments: list[str] = []

    if done_names:
        done_str = ", ".join(done_names)
        if error_parts:
            done_str += " done"
        segments.append(done_str)

    segments.extend(error_parts)
    segments.extend(notable_skips)

    return "; ".join(segments)


def _organize_detail(
    *,
    source: Path,
    target: Path,
    output_root: Path,
    action: str,
    dry_run: bool,
) -> str:
    """Build the context-aware detail string for an organize verdict.

    Shows only what changed: new filename, new folder, or both.
    """
    if str(source) == str(target):
        return "already at target"

    folder_changed = str(source.parent) != str(target.parent)
    name_changed = source.name != target.name

    if folder_changed and name_changed:
        try:
            rel = target.relative_to(output_root)
        except ValueError:
            rel = target
        base = str(rel)
    elif folder_changed:
        try:
            rel = target.parent.relative_to(output_root)
        except ValueError:
            rel = target.parent
        base = str(rel) + "/"
    elif name_changed:
        base = target.name
    else:
        return "already at target"

    if dry_run:
        return f"would {action} to {base}"
    return base


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
            display = r.display_name or r.name
            parts.append(status_text(r.status, display, r.detail or ""))
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
        self.console.print(summary_panel(counts, log_path=log_path))


class OrganizeContractProgress:
    """Contract-compliant progress output for pure organize runs (no --enrich)."""

    def __init__(
        self,
        total: int,
        console: Console | None = None,
        quiet: bool = False,
        verbose: bool = False,
        *,
        output_root: Path,
        dry_run: bool,
        action: str,
        layout: str,
    ):
        self.total = total
        self.console = console or make_console()
        self.quiet = quiet
        self.verbose = verbose
        self.output_root = output_root
        self.dry_run = dry_run
        self.action = action
        self.layout = layout
        self._file_index = 0
        self._stats: dict[str, int] = {
            "done": 0, "up_to_date": 0, "preview": 0,
            "skipped": 0, "error": 0,
        }
        self._destinations: dict[str, int] = {}
        self._skipped_reasons: dict[str, int] = {}
        self._errors: list[tuple[str, str]] = []

    def print_header(
        self,
        command: str,
        rows: dict[str, str],
        missing_tools: list[str] | None = None,
    ) -> None:
        """Print the run header (same as ProgressPrinter)."""
        self.console.print(header_panel(f"CrateDigger: {command}", rows))
        if missing_tools:
            for tool in missing_tools:
                self.console.print(
                    f"  [yellow]Warning: {tool} not found"
                    f" (some features may be limited)[/yellow]"
                )

    def file_start(self, filename: Path, target_folder: str) -> None:
        """No-op. The contract has no per-file preamble; verdict is the only line."""
        pass

    def file_done(
        self,
        source: Path,
        media_file,
        op,
        result: OperationResult,
        elapsed_s: float,
    ) -> None:
        """Emit one verdict line for a completed organize operation."""
        self._file_index += 1

        if result.status == "error":
            vstatus = "error"
            detail = result.detail or "unknown error"
            self._stats["error"] += 1
            self._errors.append((source.name, detail))
        elif result.status == "skipped" and str(source) == str(op.target):
            vstatus = "up-to-date"
            detail = "already at target"
            self._stats["up_to_date"] += 1
        elif result.status == "skipped":
            vstatus = "skipped"
            detail = result.detail or "skipped"
            self._stats["skipped"] += 1
            self._skipped_reasons[detail] = self._skipped_reasons.get(detail, 0) + 1
        else:
            vstatus = "done"
            detail = _organize_detail(
                source=source, target=op.target,
                output_root=self.output_root,
                action=self.action, dry_run=False,
            )
            self._stats["done"] += 1
            self._record_destination(op.target)

        if self.quiet:
            return

        console_width = self.console.size.width if self.console.size else 120
        self.console.print(verdict(
            status=vstatus, index=self._file_index, total=self.total,
            filename=source.name, detail_line=detail, elapsed_s=elapsed_s,
            width=console_width,
        ))

        if self.verbose and vstatus in ("done", "up-to-date"):
            self._print_metadata(media_file, op)

    def file_preview(
        self,
        source: Path,
        media_file,
        target: Path,
    ) -> None:
        """Emit one preview verdict line for a dry-run file."""
        self._file_index += 1
        detail = _organize_detail(
            source=source, target=target,
            output_root=self.output_root,
            action=self.action, dry_run=True,
        )
        if detail == "already at target":
            vstatus = "up-to-date"
            self._stats["up_to_date"] += 1
        else:
            vstatus = "preview"
            self._stats["preview"] += 1
            self._record_destination(target)

        if self.quiet:
            return

        console_width = self.console.size.width if self.console.size else 120
        self.console.print(verdict(
            status=vstatus, index=self._file_index, total=self.total,
            filename=source.name, detail_line=detail, elapsed_s=0.0,
            width=console_width,
        ))

        if self.verbose and vstatus == "preview":
            self._print_metadata(media_file, None)

    def _record_destination(self, target: Path) -> None:
        """Record a target's folder for the destinations summary breakdown."""
        try:
            rel = target.parent.relative_to(self.output_root)
            folder = str(rel) if str(rel) != "." else "./"
        except ValueError:
            folder = str(target.parent)
        self._destinations[folder] = self._destinations.get(folder, 0) + 1

    def _print_metadata(self, media_file, op) -> None:
        """Emit a dim verbose metadata line under the verdict."""
        parts = [media_file.content_type]
        parts.append(f"layout: {self.layout}")
        if op is not None and getattr(op, "sidecars_moved", 0) > 0:
            parts.append(f"{op.sidecars_moved} sidecars moved")
        self.console.print(f"    [dim]{' . '.join(parts)}[/dim]")

    def record_results(self, results: list[OperationResult]) -> None:
        """No-op. Stats are tracked inline in file_done/file_preview."""
        pass

    def print_summary(self, elapsed_s: float | None = None, log_path: Path | None = None) -> None:
        """Print the organize summary panel."""
        self.console.print()
        self.console.print(organize_summary_panel(
            stats=self._stats,
            destinations=self._destinations or None,
            skipped_reasons=self._skipped_reasons or None,
            errors=self._errors or None,
            elapsed_s=elapsed_s,
        ))


class EnrichContractProgress:
    """Contract-compliant progress output for the enrich command."""

    _STATUS_ICONS = {
        "done": "[green]\u2713[/green]",
        "skipped": "[dim]-[/dim]",
        "error": "[red]\u2717[/red]",
    }

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
        self._file_stats: dict[str, int] = {"done": 0, "up_to_date": 0, "error": 0}
        self._op_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._errors: list[tuple[str, str, str]] = []
        self._unresolved_artists: set[str] = set()

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
                self.console.print(
                    f"  [yellow]Warning: {tool} not found"
                    f" (some features may be limited)[/yellow]"
                )

    def file_start(self, filename: Path, target_folder: str) -> None:
        """No-op. The contract uses verdict lines only."""
        pass

    def file_done(
        self,
        source: Path,
        results: list[OperationResult],
        elapsed_s: float,
    ) -> None:
        """Emit a verdict block for a completed enrich file."""
        self._file_index += 1

        badge = _enrich_badge(results)
        detail = _enrich_detail(results)

        # Track file-level stats
        if badge == "up-to-date":
            self._file_stats["up_to_date"] += 1
        elif badge == "error":
            self._file_stats["error"] += 1
        else:
            self._file_stats["done"] += 1

        # Track per-operation counts and errors
        for r in results:
            op_label = r.display_name or r.name
            self._op_counts[op_label][r.status] += 1
            if r.status == "error":
                self._errors.append((source.name, op_label, r.detail or ""))

        if self.quiet:
            return

        console_width = self.console.size.width if self.console.size else 120
        self.console.print(verdict(
            status=badge,
            index=self._file_index,
            total=self.total,
            filename=source.name,
            detail_line=detail,
            elapsed_s=elapsed_s,
            width=console_width,
        ))

        if self.verbose:
            self._print_op_breakdown(results)

    def _print_op_breakdown(self, results: list[OperationResult]) -> None:
        """Print a dim per-operation breakdown line for verbose mode."""
        for r in results:
            icon = self._STATUS_ICONS.get(r.status, "?")
            parts = [f"    {icon} {r.display_name or r.name}"]
            if r.detail:
                parts.append(f": {r.detail}")
            self.console.print("".join(parts), style="dim")

    def record_results(self, results: list[OperationResult]) -> None:
        """No-op. Stats are tracked inline in file_done."""
        pass

    def print_summary(self, elapsed_s: float | None = None, log_path: Path | None = None) -> None:
        """Print the enrich summary panel."""
        self.console.print()
        self.console.print(enrich_summary_panel(
            file_stats=self._file_stats,
            op_counts=dict(self._op_counts),
            errors=self._errors or None,
            unresolved_count=len(self._unresolved_artists),
            elapsed_s=elapsed_s,
        ))


class OrganizeEnrichProgress:
    """Composite progress for organize --enrich: emits organize verdict then enrich verdict per file."""

    def __init__(self, organize: OrganizeContractProgress, enrich: EnrichContractProgress):
        self.organize = organize
        self.enrich = enrich

    @property
    def total(self):
        return self.organize.total

    @total.setter
    def total(self, value):
        self.organize.total = value
        self.enrich.total = value

    def print_header(self, command, rows, missing_tools=None):
        self.organize.print_header(command, rows, missing_tools)

    def file_start(self, filename, target_folder):
        pass  # No-op, verdicts are the output

    def file_preview(self, source, media_file, target):
        """Delegate to organize preview only (no enrich ops exist in dry-run)."""
        self.organize.file_preview(source=source, media_file=media_file, target=target)

    def record_results(self, results):
        pass  # Tracked inline by the runner calling organize/enrich file_done
