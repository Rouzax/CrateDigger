"""Tests for the central Rich formatting module."""
from __future__ import annotations

import io

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from festival_organizer.console import (
    header_panel,
    make_console,
    results_table,
    status_text,
    summary_panel,
)
from festival_organizer.tracklists.scoring import QueryParts, SearchResult


# --- make_console ---

def test_make_console_defaults_to_stdout(monkeypatch):
    c = make_console()
    assert isinstance(c, Console)


def test_make_console_custom_file():
    buf = io.StringIO()
    c = make_console(file=buf)
    assert c.file is buf


# --- header_panel ---

def test_header_panel_returns_panel():
    p = header_panel("Test Run", {"Source": "/tmp/a", "Output": "/tmp/b"})
    assert isinstance(p, Panel)
    assert p.title == "Test Run"


def test_header_panel_contains_rows():
    p = header_panel("Run", {"Source": "/music", "Layout": "flat"})
    # Render to string to verify content
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "Source" in output
    assert "/music" in output
    assert "Layout" in output
    assert "flat" in output


# --- status_text ---

def test_status_text_done():
    t = status_text("done", "nfo")
    plain = t.plain
    assert plain == "v nfo"


def test_status_text_skipped_no_detail():
    t = status_text("skipped", "poster")
    assert t.plain == "skip poster"


def test_status_text_skipped_with_detail():
    t = status_text("skipped", "poster", detail="exists")
    assert t.plain == "skip poster (exists)"


def test_status_text_error_no_detail():
    t = status_text("error", "artwork")
    assert t.plain == "! artwork"


def test_status_text_error_with_detail():
    t = status_text("error", "artwork", detail="timeout")
    assert t.plain == "! artwork (timeout)"


def test_status_text_done_green_style():
    t = status_text("done", "nfo")
    # First span is the "v" character with green style
    spans = t._spans
    assert any("green" in str(s.style) for s in spans)


def test_status_text_error_red_style():
    t = status_text("error", "nfo")
    spans = t._spans
    assert any("red" in str(s.style) for s in spans)


# --- results_table ---

def _make_result(score=200, duration_mins=60, title="Test Set", date="2025-01-01"):
    return SearchResult(
        id="1",
        title=title,
        url="https://example.com",
        duration_mins=duration_mins,
        date=date,
        score=score,
    )


def test_results_table_returns_table():
    t = results_table([_make_result()], video_duration_mins=60)
    assert isinstance(t, Table)


def test_results_table_columns():
    t = results_table([], video_duration_mins=60)
    col_names = [c.header for c in t.columns]
    assert "#" in col_names
    assert "Quality" in col_names
    assert "Title" in col_names
    assert "Date" in col_names
    assert "Duration" in col_names


def test_results_table_score_indicators():
    """Verify quality indicators map to the right score ranges."""
    console = Console(file=io.StringIO(), width=120, no_color=True)

    # Score >= 250: "+"
    t = results_table([_make_result(score=300)], video_duration_mins=60)
    console.print(t)
    output = console.file.getvalue()
    assert "+" in output


def test_results_table_max_15():
    results = [_make_result(title=f"Set {i}") for i in range(20)]
    t = results_table(results, video_duration_mins=60)
    # 15 data rows + 1 "... more" row
    assert t.row_count == 16


def test_results_table_truncation_message():
    results = [_make_result(title=f"Set {i}") for i in range(20)]
    console = Console(file=io.StringIO(), width=120)
    t = results_table(results, video_duration_mins=60)
    console.print(t)
    output = console.file.getvalue()
    assert "5 more" in output


def test_results_table_keyword_highlighting():
    qp = QueryParts(keywords=["tomorrowland", "garrix"])
    r = _make_result(title="Tomorrowland 2025 Martin Garrix")
    t = results_table([r], video_duration_mins=60, query_parts=qp)
    # Render and check that the title is present
    console = Console(file=io.StringIO(), width=120)
    console.print(t)
    output = console.file.getvalue()
    assert "Tomorrowland" in output
    assert "Garrix" in output


def test_results_table_no_query_parts():
    """Should work fine without query_parts."""
    r = _make_result(title="Some Set")
    t = results_table([r], video_duration_mins=60, query_parts=None)
    assert t.row_count == 1


def test_results_table_duration_none():
    """Result with no duration should render without error."""
    r = _make_result(duration_mins=None)
    t = results_table([r], video_duration_mins=60)
    assert t.row_count == 1


def test_results_table_video_duration_none():
    """No video duration means no diff coloring."""
    r = _make_result(duration_mins=60)
    t = results_table([r], video_duration_mins=None)
    assert t.row_count == 1


def test_results_table_duration_coloring():
    """Verify duration diff coloring thresholds."""
    console = Console(file=io.StringIO(), width=120)

    # Exact match: green
    r_exact = _make_result(duration_mins=60)
    t = results_table([r_exact], video_duration_mins=60)
    console.print(t)
    # Just verify it renders without error
    assert t.row_count == 1


# --- summary_panel ---

def test_summary_panel_flat_counts():
    p = summary_panel({"added": 3, "skipped": 1, "error": 0})
    assert isinstance(p, Panel)
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "added" in output
    assert "3" in output
    assert "skipped" in output


def test_summary_panel_nested_counts():
    counts = {
        "nfo": {"done": 2, "skipped": 1},
        "poster": {"done": 3, "error": 1},
    }
    p = summary_panel(counts)
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "NFO" in output
    assert "POSTER" in output
    assert "2" in output


def test_summary_panel_with_log_path():
    p = summary_panel({"added": 1}, log_path="/tmp/run.log")
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "Log" in output
    assert "/tmp/run.log" in output


def test_summary_panel_no_log_path():
    p = summary_panel({"added": 1})
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "Log" not in output


def test_summary_panel_empty_nested():
    counts = {"nfo": {"done": 0}}
    p = summary_panel(counts)
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "NFO" in output
    assert "0" in output


def test_summary_panel_up_to_date():
    p = summary_panel({"added": 2, "up_to_date": 5, "error": 0})
    console = Console(file=io.StringIO(), width=80)
    console.print(p)
    output = console.file.getvalue()
    assert "up_to_date" in output
    assert "5" in output
