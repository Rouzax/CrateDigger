"""Central Rich formatting module.

All Rich usage in the project flows through this module.
Provides console creation and reusable widget builders for
headers, result tables, status indicators, and summaries.
"""
from __future__ import annotations

import re
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
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
        for op_name, statuses in sorted(counts.items()):
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
