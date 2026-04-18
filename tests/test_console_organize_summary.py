"""Tests for organize_summary_panel."""
import io
from rich.console import Console
from rich.panel import Panel
from festival_organizer.console import organize_summary_panel


def _render(renderable) -> str:
    buf = io.StringIO()
    Console(file=buf, width=120, no_color=True).print(renderable)
    return buf.getvalue()


def test_returns_panel():
    p = organize_summary_panel(
        stats={"done": 3, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
    )
    assert isinstance(p, Panel)


def test_stats_row_shows_all_counts():
    p = organize_summary_panel(
        stats={"done": 3, "up_to_date": 1, "preview": 0, "skipped": 2, "error": 1},
    )
    out = _render(p)
    assert "done" in out and "3" in out
    assert "up_to_date" in out and "1" in out
    assert "skipped" in out and "2" in out
    assert "error" in out and "1" in out


def test_destinations_breakdown():
    p = organize_summary_panel(
        stats={"done": 5, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
        destinations={"Festivals/Ultra Miami 2026": 3, "Artists/Afrojack": 2},
    )
    out = _render(p)
    assert "Festivals/Ultra Miami 2026" in out
    assert "3" in out
    assert "Artists/Afrojack" in out


def test_destinations_truncation_at_10():
    dests = {f"Festival/{i}": i + 1 for i in range(15)}
    p = organize_summary_panel(
        stats={"done": 15, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
        destinations=dests,
    )
    out = _render(p)
    assert "+5 more" in out


def test_skipped_reasons_shown():
    p = organize_summary_panel(
        stats={"done": 0, "up_to_date": 0, "preview": 0, "skipped": 3, "error": 0},
        skipped_reasons={"not a video": 2, "unrecognized": 1},
    )
    out = _render(p)
    assert "not a video" in out
    assert "2" in out


def test_skipped_reasons_omitted_when_empty():
    p = organize_summary_panel(
        stats={"done": 1, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
    )
    out = _render(p)
    assert "not a video" not in out


def test_errors_list_shown():
    p = organize_summary_panel(
        stats={"done": 0, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 2},
        errors=[("file1.mkv", "Permission denied"), ("file2.mkv", "Disk full")],
    )
    out = _render(p)
    assert "file1.mkv" in out
    assert "Permission denied" in out


def test_errors_capped_at_10():
    errors = [(f"file{i}.mkv", "err") for i in range(15)]
    p = organize_summary_panel(
        stats={"done": 0, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 15},
        errors=errors,
    )
    out = _render(p)
    assert "+5 more" in out


def test_elapsed_shown():
    p = organize_summary_panel(
        stats={"done": 1, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
        elapsed_s=83.2,
    )
    out = _render(p)
    assert "Elapsed" in out
    assert "1m 23s" in out


def test_elapsed_omitted_when_none():
    p = organize_summary_panel(
        stats={"done": 1, "up_to_date": 0, "preview": 0, "skipped": 0, "error": 0},
    )
    out = _render(p)
    assert "Elapsed" not in out
