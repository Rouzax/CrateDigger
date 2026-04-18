"""Tests for library_sync_summary_line."""
from festival_organizer.console import library_sync_summary_line


def test_shape_includes_name_and_stats():
    line = library_sync_summary_line(
        "Kodi", {"refreshed": 5, "not yet in library": 2}, elapsed_s=3.4,
    )
    plain = line.plain
    assert "done" in plain
    assert "Kodi sync" in plain
    assert "refreshed 5" in plain
    assert "not yet in library 2" in plain
    assert "3.4s" in plain


def test_short_elapsed_omitted():
    line = library_sync_summary_line(
        "Kodi", {"refreshed": 3}, elapsed_s=0.2,
    )
    assert "0.2s" not in line.plain


def test_generic_name():
    line = library_sync_summary_line(
        "Lyrion", {"refreshed": 1}, elapsed_s=1.0,
    )
    assert "Lyrion sync" in line.plain


def test_zero_stats_omitted():
    line = library_sync_summary_line(
        "Kodi", {"refreshed": 5, "not yet in library": 0}, elapsed_s=1.0,
    )
    assert "not yet in library" not in line.plain
