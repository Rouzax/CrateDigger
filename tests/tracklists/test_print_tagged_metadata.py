"""Tests for _print_tagged_metadata_from_stored."""
import io
from pathlib import Path

from rich.console import Console


def test_print_tagged_metadata_from_stored_happy_path(monkeypatch):
    """Prints a dim Tagged: line with artists, first festival, stage."""
    from festival_organizer.tracklists import cli_handler

    fake_stored = {
        "artists": "Armin van Buuren|Marlon Hoffstadt",
        "festival": "Ultra Music Festival Miami|Something Else",
        "stage": "ASOT Worldwide Stage",
        "url": "https://example/tl/abc",
    }
    monkeypatch.setattr(cli_handler, "extract_stored_tracklist_info",
                        lambda p: fake_stored)

    buf = io.StringIO()
    con = Console(file=buf, no_color=True, width=120)
    cli_handler._print_tagged_metadata_from_stored(Path("fake.mkv"), con)
    out = buf.getvalue()
    assert "Tagged:" in out
    assert "Armin van Buuren, Marlon Hoffstadt" in out
    assert "Ultra Music Festival Miami" in out
    assert "ASOT Worldwide Stage" in out


def test_print_tagged_metadata_from_stored_empty_noop(monkeypatch):
    """When extract_stored_tracklist_info returns None/empty, prints nothing."""
    from festival_organizer.tracklists import cli_handler

    monkeypatch.setattr(cli_handler, "extract_stored_tracklist_info",
                        lambda p: None)

    buf = io.StringIO()
    con = Console(file=buf, no_color=True, width=120)
    cli_handler._print_tagged_metadata_from_stored(Path("fake.mkv"), con)
    assert "Tagged:" not in buf.getvalue()


def test_print_tagged_metadata_from_stored_prefers_festival_over_radio(monkeypatch):
    """Festival takes precedence over conference/radio."""
    from festival_organizer.tracklists import cli_handler

    fake_stored = {
        "artists": "Solo DJ",
        "festival": "Big Fest",
        "radio": "Some Radio Show",
    }
    monkeypatch.setattr(cli_handler, "extract_stored_tracklist_info",
                        lambda p: fake_stored)

    buf = io.StringIO()
    con = Console(file=buf, no_color=True, width=120)
    cli_handler._print_tagged_metadata_from_stored(Path("fake.mkv"), con)
    out = buf.getvalue()
    assert "Big Fest" in out
    assert "Some Radio Show" not in out
