from pathlib import Path
from festival_organizer.models import MediaFile, FileAction, build_display_title


def test_media_file_defaults():
    mf = MediaFile(source_path=Path("test.mkv"))
    assert mf.artist == ""
    assert mf.festival == ""
    assert mf.year == ""
    assert mf.content_type == ""
    assert mf.extension == ""
    assert mf.duration_seconds is None
    assert mf.has_cover is False


def test_media_file_with_values():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    assert mf.artist == "Martin Garrix"
    assert mf.festival == "AMF"


def test_media_file_resolution_property():
    mf = MediaFile(source_path=Path("test.mkv"), width=3840, height=2160)
    assert mf.resolution == "3840x2160"

    mf2 = MediaFile(source_path=Path("test.mkv"))
    assert mf2.resolution == ""


def test_media_file_duration_formatted():
    mf = MediaFile(source_path=Path("test.mkv"), duration_seconds=7260.0)
    assert mf.duration_formatted == "121m00s"

    mf2 = MediaFile(source_path=Path("test.mkv"))
    assert mf2.duration_formatted == ""


def test_media_file_new_fields_default_empty():
    """New enrichment fields default to empty strings."""
    mf = MediaFile(source_path=Path("test.mkv"))
    assert mf.fanart_url == ""
    assert mf.clearlogo_url == ""
    assert mf.enriched_at == ""


def test_display_artist_defaults_empty():
    mf = MediaFile(source_path=Path("test.mkv"))
    assert mf.display_artist == ""


def test_mediafile_has_place_fields():
    from festival_organizer.models import MediaFile
    from pathlib import Path
    mf = MediaFile(source_path=Path("/tmp/x.mkv"))
    assert mf.place == ""
    assert mf.place_kind == ""
    assert mf.venue_full == ""


def test_display_artist_set_explicitly():
    mf = MediaFile(source_path=Path("test.mkv"), display_artist="Martin Garrix & Alesso")
    assert mf.display_artist == "Martin Garrix & Alesso"


def test_build_display_title_uses_place_for_festival_kind():
    mf = MediaFile(
        source_path=Path("x.mkv"),
        artist="Armin van Buuren",
        place="Tomorrowland",
        place_kind="festival",
        content_type="festival_set",
    )
    assert build_display_title(mf) == "Armin van Buuren @ Tomorrowland"


def test_build_display_title_uses_place_for_venue_kind():
    """Venue-routed sets must show '@ Venue' in the title (not just artist)."""
    mf = MediaFile(
        source_path=Path("x.mkv"),
        artist="Fred again..",
        place="Alexandra Palace",
        place_kind="venue",
        content_type="festival_set",
    )
    assert build_display_title(mf) == "Fred again.. @ Alexandra Palace"


def test_build_display_title_uses_place_for_location_kind():
    """Location-routed sets show '@ Location' in the title."""
    mf = MediaFile(
        source_path=Path("x.mkv"),
        artist="DJ Example",
        place="Some Bar, Berlin",
        place_kind="location",
        content_type="festival_set",
    )
    assert build_display_title(mf) == "DJ Example @ Some Bar, Berlin"


def test_build_display_title_falls_back_to_artist_only_for_artist_kind():
    """Artist-fallback sets render as just the artist (no '@ Artist' duplicate)."""
    mf = MediaFile(
        source_path=Path("x.mkv"),
        artist="Fred again..",
        place="Fred again..",
        place_kind="artist",
        content_type="festival_set",
    )
    assert build_display_title(mf) == "Fred again.."


def test_build_display_title_with_stage_and_venue():
    """Stage with venue-routed set: 'Artist @ Stage, Venue'."""
    mf = MediaFile(
        source_path=Path("x.mkv"),
        artist="Fred again..",
        place="Alexandra Palace",
        place_kind="venue",
        stage="USB002",
        content_type="festival_set",
    )
    assert build_display_title(mf) == "Fred again.. @ USB002, Alexandra Palace"


def test_build_display_title_with_set_title_and_venue():
    """Set title appended to venue-routed place segment."""
    mf = MediaFile(
        source_path=Path("x.mkv"),
        artist="Bicep",
        place="Printworks",
        place_kind="venue",
        set_title="Closing Set",
        content_type="festival_set",
    )
    assert build_display_title(mf) == "Bicep @ Printworks Closing Set"


def test_file_action_defaults():
    mf = MediaFile(source_path=Path("src.mkv"))
    fa = FileAction(
        source=Path("src.mkv"),
        target=Path("dst.mkv"),
        media_file=mf,
    )
    assert fa.action == "move"
    assert fa.status == "pending"
    assert fa.error == ""
