from pathlib import Path
from festival_organizer.models import MediaFile, FileAction


def test_media_file_defaults():
    mf = MediaFile(source_path=Path("test.mkv"))
    assert mf.artist == ""
    assert mf.festival == ""
    assert mf.year == ""
    assert mf.content_type == ""
    assert mf.extension == ""
    assert mf.duration_seconds is None
    assert mf.has_cover == False


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


def test_display_artist_set_explicitly():
    mf = MediaFile(source_path=Path("test.mkv"), display_artist="Martin Garrix & Alesso")
    assert mf.display_artist == "Martin Garrix & Alesso"


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
