from festival_organizer.tracklists.api import Track, TracklistExport


def test_track_fields():
    t = Track(start_ms=120_000, raw_text="AFROJACK - ID",
              artist_slugs=["afrojack"], genres=["House"])
    assert t.start_ms == 120_000
    assert t.raw_text == "AFROJACK - ID"
    assert t.artist_slugs == ["afrojack"]
    assert t.genres == ["House"]


def test_tracklist_export_has_tracks_field():
    te = TracklistExport(lines=[], url="", title="", tracks=[])
    assert te.tracks == []


def test_tracklist_export_tracks_defaults_to_empty():
    # tracks field should have a default_factory so existing call sites keep working
    te = TracklistExport(lines=[], url="", title="")
    assert te.tracks == []


def test_tracklist_export_date_defaults_to_empty_string():
    """The date field defaults to empty so existing call sites keep working."""
    te = TracklistExport(lines=[], url="", title="")
    assert te.date == ""


def test_tracklist_export_date_accepts_iso_date():
    """The date field carries the event date captured from the h1 tail."""
    te = TracklistExport(lines=[], url="", title="", date="2025-10-24")
    assert te.date == "2025-10-24"
