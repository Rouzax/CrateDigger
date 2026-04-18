"""Central Rich formatting module.

All Rich usage in the project flows through this module.
Provides console creation and reusable widget builders for
headers, result tables, status indicators, and summaries.
"""
from __future__ import annotations

import re
import sys
import threading

from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

_MAX_RESULTS = 15


def make_console(file=None) -> Console:
    """Create a Console writing to the given file (default stdout).

    Rich auto-detects isatty() on the file descriptor.
    Highlighting is disabled so Rich does not colorize numbers,
    UUIDs, or other patterns in user-provided content.
    """
    return Console(file=file or sys.stdout, highlight=False)


def suppression_enabled(
    console: Console,
    *,
    quiet: bool,
    verbose: bool,
    debug: bool,
) -> bool:
    """Return True when transient live display must be disabled.

    Rules (single source of truth for every command):
    - stdout is not a TTY
    - --quiet
    - --verbose or --debug (log lines would collide with Live)

    When True, commands still emit header/verdict/summary prints;
    only transient spinners are skipped.
    """
    if not console.is_terminal:
        return True
    return bool(quiet or verbose or debug)


def header_panel(title: str, rows: dict[str, str]) -> Panel:
    """Bordered header box with a title and key-value rows."""
    body = Text()
    for i, (key, value) in enumerate(rows.items()):
        if i > 0:
            body.append("\n")
        body.append(f"{key}:  ", style="bold")
        body.append(str(value))
    return Panel(body, title=title, expand=True)


def _score_style(score: float) -> tuple[str, str]:
    """Return (indicator, style) for a score value."""
    if score >= 250:
        return "+", "bold green"
    if score >= 150:
        return "~", "yellow"
    if score >= 80:
        return "?", "yellow"
    return "-", "red"


def _format_elapsed(seconds: float) -> str:
    """Human-readable elapsed time for summary panels."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}m {secs}s"


def _duration_style(diff_mins: float) -> str:
    """Return a style string for a duration difference."""
    abs_diff = abs(diff_mins)
    if abs_diff <= 2:
        return "green"
    if abs_diff <= 10:
        return "yellow"
    return "red"


def _highlight_keywords(title: str, keywords: list[str]) -> Text:
    """Wrap matched keywords in bold, processed longest-first."""
    text = Text(title)
    if not keywords:
        return text

    # Sort longest-first to avoid partial overlap
    sorted_kw = sorted((kw for kw in keywords if kw), key=len, reverse=True)
    # Track which character positions are already highlighted
    highlighted = [False] * len(title)

    for kw in sorted_kw:
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        for m in pattern.finditer(title):
            start, end = m.start(), m.end()
            if any(highlighted[start:end]):
                continue
            for i in range(start, end):
                highlighted[i] = True
            text.stylize("bold", start, end)

    return text


def results_table(
    results,
    video_duration_mins: int | float | None,
    query_parts=None,
) -> Table:
    """Chapter search results table.

    Columns: #, Quality, Title, Date, Duration.
    Shows at most 15 results.
    """
    table = Table(show_header=True, expand=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("Quality", justify="center", width=7)
    table.add_column("Title", ratio=1)
    table.add_column("Date", width=10)
    table.add_column("Duration", justify="right", width=10)

    keywords = query_parts.keywords if query_parts else []

    for idx, r in enumerate(results[:_MAX_RESULTS], 1):
        indicator, style = _score_style(r.score)
        quality = Text(indicator, style=style)

        title_text = _highlight_keywords(r.title, keywords)

        date_str = r.date or ""

        if r.duration_mins is not None:
            dur_str = f"{r.duration_mins}m"
            if video_duration_mins is not None:
                diff = r.duration_mins - video_duration_mins
                dur_style = _duration_style(diff)
                dur_text = Text(dur_str, style=dur_style)
            else:
                dur_text = Text(dur_str)
        else:
            dur_text = Text("")

        table.add_row(str(idx), quality, title_text, date_str, dur_text)

    return table


def status_text(status: str, name: str, detail: str = "") -> Text:
    """Colored operation result indicator.

    Status must be one of: done, skipped, error.
    """
    text = Text()
    if status == "done":
        text.append("\u2714  ", style="green")
        text.append(name)
    elif status == "skipped":
        text.append("\u25cb  ", style="dim")
        text.append(name)
        if detail:
            text.append(f" ({detail})", style="dim")
    elif status == "error":
        text.append("\u2718  ", style="red")
        text.append(name)
        if detail:
            text.append(f" ({detail})", style="red")
    return text


def summary_panel(counts: dict, log_path=None) -> Panel:
    """Final run summary in a panel.

    Handles two shapes:
    - Flat counts (chapters command): {"added": 3, "skipped": 1, "error": 0}
    - Nested counts (progress printer): {"nfo": {"done": 2, "skipped": 1}}
    """
    body = Text()
    is_nested = any(isinstance(v, dict) for v in counts.values())

    if is_nested:
        first = True
        _WORKFLOW_ORDER = ["organize", "nfo", "art", "fanart", "posters", "tags"]
        ordered_keys = [k for k in _WORKFLOW_ORDER if k in counts]
        ordered_keys += [k for k in counts if k not in _WORKFLOW_ORDER]
        for op_name, statuses in ((k, counts[k]) for k in ordered_keys):
            if not first:
                body.append("\n")
            first = False
            done = statuses.get("done", 0)
            skipped = statuses.get("skipped", 0)
            error = statuses.get("error", 0)
            label = op_name.upper()
            body.append(f"{label}: ", style="bold")
            body.append(f"{done}", style="green")
            if skipped:
                body.append(f"  skipped {skipped}", style="dim")
            if error:
                body.append(f"  error {error}", style="red")
    else:
        parts = []
        for key, value in counts.items():
            parts.append((key, value))
        first = True
        for key, value in parts:
            if not first:
                body.append("  ")
            first = False
            style = "green" if key in ("added", "done", "up_to_date") else (
                "cyan" if key == "updated" else (
                    "red" if key == "error" else "dim"
                )
            )
            body.append(f"{key}: ", style="bold")
            body.append(str(value), style=style)

    if log_path:
        body.append("\n")
        body.append("Log: ", style="bold")
        body.append(str(log_path), style="dim")

    return Panel(body, title="Summary", expand=True)


class StepProgress:
    """Transient live spinner with a step label (and optional sub-counter).

    Drives feedback for blocking ops like HTTP calls, subprocess writes,
    and inter-file throttling. Auto-disables when ``enabled=False``,
    matching the product-wide suppression rules (see ``suppression_enabled``).

    Usage::

        with StepProgress(console, enabled=not suppressed) as sp:
            sp.update("Searching 1001TL", filename=fname)
            results = session.search(...)
            sp.update("Fetching tracklist", filename=fname)
            ...
    """

    def __init__(self, console: Console, enabled: bool = True) -> None:
        self._console = console
        self._enabled = enabled
        self._lock = threading.Lock()
        self.step = ""
        self.filename: str | None = None
        self.current = 0
        self.total = 0
        self.live: Live | None = None

    def _render(self) -> Text:
        text = Text()
        label = self.step
        if self.total > 0:
            label = f"{label} {self.current}/{self.total}"
        text.append(label, style="cyan")
        if self.filename:
            text.append(f"  {self.filename}", style="dim")
        return text

    def update(
        self,
        step: str,
        *,
        filename: str | None = None,
        current: int = 0,
        total: int = 0,
    ) -> None:
        with self._lock:
            self.step = step
            if filename is not None:
                self.filename = filename
            self.current = current
            self.total = total
            if self.live is not None:
                self.live.update(Spinner("dots", text=self._render()))

    def start(self) -> None:
        if not self._enabled or self.live is not None:
            return
        self.live = Live(
            Spinner("dots", text=self._render()),
            console=self._console,
            refresh_per_second=10,
            transient=True,
        )
        self.live.__enter__()

    def stop(self) -> None:
        if self.live is not None:
            self.live.__exit__(None, None, None)
            self.live = None

    def __enter__(self) -> "StepProgress":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


_VERDICT_STYLES = {
    "done":       ("done",        "green"),
    "updated":    ("updated",     "cyan"),
    "up-to-date": ("up-to-date",  "dim green"),
    "preview":    ("preview",     "cyan"),
    "skipped":    ("skipped",     "yellow"),
    "error":      ("error",       "red"),
}

_VERDICT_BADGE_WIDTH = 14
_ELAPSED_THRESHOLD_S = 0.5


def _truncate_preserving_id(name: str, max_len: int) -> str:
    """Truncate a filename with an ellipsis while keeping a trailing
    YouTube-style [id].ext suffix visible. Falls back to plain middle
    truncation when no bracketed ID is present.
    """
    if len(name) <= max_len:
        return name
    m = re.search(r"\s*\[[^\]]+\]\.[A-Za-z0-9]+$", name)
    if m:
        suffix = m.group(0)
        head_len = max_len - len(suffix) - 1
        if head_len <= 1:
            return "\u2026" + suffix
        return name[:head_len] + "\u2026" + suffix
    head = max_len // 2 - 1
    tail = max_len - head - 1
    return name[:head] + "\u2026" + name[-tail:]


def verdict(
    *,
    status: str,
    index: int,
    total: int,
    filename: str,
    detail: str = "",
    elapsed_s: float,
    width: int | None = None,
    detail_line: str | None = None,
) -> Text:
    """Padded badge + [i/N] + filename + detail + elapsed.

    When detail_line is None (default), produces a single line with an
    arrow separator before the detail text.

    When detail_line is provided, produces a two-line block: line 1 has
    the badge, counter, filename, and elapsed; line 2 has detail_line
    content aligned under the filename. The detail parameter is ignored
    in this mode.

    width: when supplied, filename is truncated to fit. When None, no
    truncation (the terminal will soft-wrap).
    """
    if status not in _VERDICT_STYLES:
        raise ValueError(f"Unknown verdict status: {status}")
    label, style = _VERDICT_STYLES[status]

    counter = f"[{index}/{total}] "
    pad = _VERDICT_BADGE_WIDTH - len(label) - 2
    if pad < 0:
        pad = 0
    fname_offset = 2 + len(label) + pad + len(counter)

    fname_display = filename
    if detail_line is not None:
        # Two-line mode: no arrow/detail on line 1, more room for filename
        if width is not None:
            budget = max(10, width - fname_offset - 10)
            fname_display = _truncate_preserving_id(filename, budget)

        text = Text()
        text.append("  ")
        text.append(label, style=style)
        if pad > 0:
            text.append(" " * pad)
        text.append(counter)
        text.append(fname_display)
        if elapsed_s >= _ELAPSED_THRESHOLD_S:
            text.append("  .  ")
            text.append(f"{elapsed_s:.1f}s", style="dim")
        text.append("\n")
        text.append(" " * fname_offset)
        text.append(detail_line)
        return text

    # Single-line mode (original behaviour)
    if width is not None:
        budget = max(10, width - _VERDICT_BADGE_WIDTH - len(counter)
                     - len(" -> ") - len(detail) - 10)
        fname_display = _truncate_preserving_id(filename, budget)

    text = Text()
    text.append("  ")
    text.append(label, style=style)
    if pad > 0:
        text.append(" " * pad)

    text.append(counter)
    text.append(fname_display)
    if detail:
        text.append("  ->  ")
        text.append(detail)
    if elapsed_s >= _ELAPSED_THRESHOLD_S:
        text.append("  .  ")
        text.append(f"{elapsed_s:.1f}s", style="dim")
    return text


def print_error(message: str, console: Console | None = None) -> None:
    """Print a styled error message.

    Uses Rich console when available, falls back to stderr.
    """
    if console:
        console.print(f"[red]Error:[/red] {escape(message)}")
    else:
        print(f"Error: {message}", file=sys.stderr)


def classification_summary_panel(
    total: int,
    festival_sets: int,
    concerts: int,
    unrecognized: list[str],
) -> Panel:
    """Dry-run classification breakdown panel."""
    body = Text()
    body.append("Festival sets: ", style="bold")
    body.append(str(festival_sets), style="green")
    body.append("\n")
    body.append("Concerts: ", style="bold")
    body.append(str(concerts), style="green")
    if unrecognized:
        body.append("\n")
        body.append("Unrecognized: ", style="bold")
        body.append(str(len(unrecognized)), style="yellow")
        for name in unrecognized:
            body.append(f"\n  {name}", style="yellow")
    return Panel(body, title="Dry Run Summary", expand=True)


def identify_summary_panel(
    stats: dict[str, int],
    tagged_count: int = 0,
    festivals: dict[str, int] | None = None,
    unmatched: list[str] | None = None,
    elapsed_s: float | None = None,
) -> Panel:
    """Summary panel for the identify command with metadata breakdown."""
    body = Text()

    # Standard stats line
    first = True
    for key, value in stats.items():
        if not first:
            body.append("  ")
        first = False
        style = "green" if key in ("added", "done", "up_to_date") else (
            "cyan" if key in ("updated", "previewed") else (
                "red" if key == "error" else "dim"
            )
        )
        body.append(f"{key}: ", style="bold")
        body.append(str(value), style=style)

    # Metadata tagged count
    if tagged_count:
        body.append(f"\n\nMetadata tagged: ", style="bold")
        body.append(str(tagged_count), style="green")
        body.append(" files")

    # Festival breakdown
    if festivals:
        body.append("\n")
        body.append("Festivals: ", style="bold")
        sorted_fests = sorted(festivals.items(), key=lambda x: -x[1])
        fest_parts = [f"{name} ({count})" for name, count in sorted_fests[:6]]
        body.append(", ".join(fest_parts))
        remaining = len(sorted_fests) - 6
        if remaining > 0:
            body.append(f", ... +{remaining} more", style="dim")

    # Unmatched files
    if unmatched:
        body.append("\n")
        body.append("Unmatched: ", style="bold")
        body.append(str(len(unmatched)), style="yellow")
        body.append(f" ({', '.join(unmatched[:5])})", style="yellow")
        if len(unmatched) > 5:
            body.append(f", ... +{len(unmatched) - 5} more", style="dim")

    if elapsed_s is not None:
        body.append("\n\n")
        body.append("Elapsed: ", style="bold")
        body.append(_format_elapsed(elapsed_s), style="dim")

    return Panel(body, title="Summary", expand=True)


def organize_summary_panel(
    stats: dict[str, int],
    destinations: dict[str, int] | None = None,
    skipped_reasons: dict[str, int] | None = None,
    errors: list[tuple[str, str]] | None = None,
    elapsed_s: float | None = None,
) -> Panel:
    """Summary panel for the organize command."""
    _stat_styles = {
        "done": "green",
        "up_to_date": "dim green",
        "preview": "cyan",
        "skipped": "yellow",
        "error": "red",
    }

    body = Text()

    # Stats row
    first = True
    for key, value in stats.items():
        if not first:
            body.append("  ")
        first = False
        body.append(f"{key}: ", style="bold")
        body.append(str(value), style=_stat_styles.get(key, "dim"))

    # Destinations breakdown
    if destinations:
        body.append("\n\n")
        body.append("Destinations:", style="bold")
        sorted_dests = sorted(destinations.items(), key=lambda x: -x[1])
        for folder, count in sorted_dests[:10]:
            body.append(f"\n  {folder}: ")
            body.append(str(count), style="green")
        remaining = len(sorted_dests) - 10
        if remaining > 0:
            body.append(f"\n  ... +{remaining} more", style="dim")

    # Skipped reasons
    if skipped_reasons:
        body.append("\n\n")
        body.append("Skipped:", style="bold")
        for reason, count in skipped_reasons.items():
            body.append(f"\n  {reason}: ")
            body.append(str(count), style="yellow")

    # Errors list
    if errors:
        body.append("\n\n")
        body.append("Errors:", style="bold")
        for filename, detail in errors[:10]:
            body.append(f"\n  {filename} -> {detail}", style="red")
        remaining = len(errors) - 10
        if remaining > 0:
            body.append(f"\n  ... +{remaining} more", style="dim")

    # Elapsed
    if elapsed_s is not None:
        body.append("\n\n")
        body.append("Elapsed: ", style="bold")
        body.append(_format_elapsed(elapsed_s), style="dim")

    return Panel(body, title="Summary", expand=True)


def library_sync_summary_line(
    name: str,
    stats: dict[str, int],
    elapsed_s: float,
) -> Text:
    """One-line contract-styled summary for a library sync sub-phase.

    Shape: ``done  <name> sync  ->  refreshed N, M not yet in library  .  Ns``
    """
    label, style = _VERDICT_STYLES["done"]

    text = Text()
    text.append("  ")
    text.append(label, style=style)
    pad = _VERDICT_BADGE_WIDTH - len(label) - 2
    if pad > 0:
        text.append(" " * pad)

    text.append(f"{name} sync")

    non_zero = [(k, v) for k, v in stats.items() if v]
    if non_zero:
        text.append("  ->  ")
        parts = [f"{k} {v}" for k, v in non_zero]
        text.append(", ".join(parts))

    if elapsed_s >= _ELAPSED_THRESHOLD_S:
        text.append("  .  ")
        text.append(f"{elapsed_s:.1f}s", style="dim")

    return text
