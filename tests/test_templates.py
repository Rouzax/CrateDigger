from pathlib import Path
from festival_organizer.templates import render_folder, render_filename
from festival_organizer.config import Config, DEFAULT_CONFIG, load_config
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_render_folder_artist_flat_festival():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG)
    assert result == "Martin Garrix"


def test_render_folder_artist_nested_festival():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="artist_nested")
    assert result == "Martin Garrix/AMF/2024"


def test_render_folder_artist_nested_concert():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Coldplay",
        title="A Head Full of Dreams",
        year="2018",
        content_type="concert_film",
    )
    result = render_folder(mf, CFG, layout_name="artist_nested")
    assert result == "Coldplay/2018 - A Head Full of Dreams"


def test_render_folder_festival_nested():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        location="Belgium",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_nested")
    # Tomorrowland has location_in_name, so becomes "Tomorrowland Belgium"
    assert result == "Tomorrowland Belgium/2025/Hardwell"


def test_render_folder_festival_flat_festival_set():
    """festival_flat layout: festival sets go into {festival}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="Tomorrowland",
        year="2024",
        content_type="festival_set",
    )
    config = load_config()
    result = render_folder(mf, config, layout_name="festival_flat")
    assert result == "Tomorrowland"


def test_render_folder_festival_flat_concert_film():
    """festival_flat layout: concerts fall back to {artist}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Adele",
        title="Live at Hyde Park",
        year="2022",
        content_type="concert_film",
    )
    config = load_config()
    result = render_folder(mf, config, layout_name="festival_flat")
    assert result == "Adele"


def test_render_folder_with_location_in_festival_name():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Alok",
        festival="Tomorrowland",
        year="2025",
        location="Brasil",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="artist_nested")
    assert result == "Alok/Tomorrowland Brasil/2025"


def test_render_folder_missing_artist():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="artist_nested")
    assert "Unknown Artist" in result


def test_render_folder_unknown_content():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Someone",
        content_type="unknown",
    )
    result = render_folder(mf, CFG, layout_name="artist_nested")
    assert "_Needs Review" in result


def test_render_filename_festival_set():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2024 - AMF - Martin Garrix.mkv"


def test_render_filename_with_set_title():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        set_title="WE1",
        location="Belgium",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Tomorrowland Belgium - Hardwell - WE1.mkv"


def test_render_filename_concert_film():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Coldplay",
        title="A Head Full of Dreams",
        year="2018",
        extension=".mkv",
        content_type="concert_film",
    )
    result = render_filename(mf, CFG)
    assert result == "Coldplay - A Head Full of Dreams.mkv"


def test_render_filename_missing_values_uses_fallbacks():
    mf = MediaFile(
        source_path=Path("mystery.mkv"),
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    # Should fall back to original filename when too much is missing
    assert result == "mystery.mkv"
