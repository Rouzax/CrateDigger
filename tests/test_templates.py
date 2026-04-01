from pathlib import Path
from festival_organizer.templates import render_folder, render_filename, _render
from festival_organizer.config import Config
from festival_organizer.models import MediaFile
from tests.conftest import TEST_CONFIG

CFG = Config(TEST_CONFIG)


# --- Folder rendering ---


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
        edition="Belgium",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_nested")
    assert result == "Tomorrowland Belgium/2025/Hardwell"


def test_render_folder_festival_flat_festival_set():
    """festival_flat layout: festival sets go into {festival}{edition}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="Tomorrowland",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_flat")
    assert result == "Tomorrowland"


def test_render_folder_festival_flat_with_edition():
    """festival_flat layout: edition appended when configured."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Alok",
        festival="Tomorrowland",
        year="2025",
        edition="Brasil",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_flat")
    assert result == "Tomorrowland Brasil"


def test_render_folder_festival_flat_concert_film():
    """festival_flat layout: concerts fall back to {artist}/."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Adele",
        title="Live at Hyde Park",
        year="2022",
        content_type="concert_film",
    )
    result = render_folder(mf, CFG, layout_name="festival_flat")
    assert result == "Adele"


def test_render_folder_with_edition_in_nested():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Alok",
        festival="Tomorrowland",
        year="2025",
        edition="Brasil",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="artist_nested")
    assert result == "Alok/Tomorrowland Brasil/2025"


def test_render_folder_edition_collapses_when_empty():
    """Edition collapses cleanly in folder paths when not present."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_nested")
    assert result == "AMF/2024/Martin Garrix"


def test_render_folder_edition_collapses_when_unknown():
    """Unknown editions are not included in folder paths."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="AMF",
        year="2024",
        edition="Netherlands",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG, layout_name="festival_nested")
    assert result == "AMF/2024/Hardwell"


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


def test_render_folder_uses_primary_artist_not_display():
    """Folder path uses primary artist, never display_artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
        content_type="festival_set",
    )
    result = render_folder(mf, CFG)
    assert result == "Martin Garrix"
    result_nested = render_folder(mf, CFG, layout_name="artist_nested")
    assert result_nested == "Martin Garrix/Red Rocks/2025"


# --- Filename rendering: festival sets ---


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
    assert result == "2024 - Martin Garrix - AMF.mkv"


def test_render_filename_with_set_title():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        set_title="WE1",
        edition="Belgium",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Hardwell - Tomorrowland Belgium - WE1.mkv"


def test_render_filename_with_stage():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        stage="Mainstage",
        edition="Belgium",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Hardwell - Tomorrowland Belgium [Mainstage].mkv"


def test_render_filename_with_stage_and_set_title():
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Hardwell",
        festival="Tomorrowland",
        year="2025",
        stage="Mainstage",
        set_title="WE1",
        edition="Belgium",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Hardwell - Tomorrowland Belgium [Mainstage] - WE1.mkv"


def test_render_filename_stage_empty_collapses():
    """When stage is empty, brackets and surrounding space collapse."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert "[" not in result
    assert result == "2024 - Martin Garrix - AMF.mkv"


def test_render_filename_no_optional_fields():
    """No stage, no set_title, no edition: clean output."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2025",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Martin Garrix - AMF.mkv"


def test_render_filename_uses_display_artist():
    """Filename uses display_artist (full B2B name), not artist (primary)."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="Martin Garrix & Alesso",
        festival="Red Rocks",
        year="2025",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2025 - Martin Garrix & Alesso - Red Rocks.mkv"


def test_render_filename_display_artist_empty_falls_back():
    """When display_artist is empty, filename falls back to artist."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        display_artist="",
        festival="AMF",
        year="2024",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2024 - Martin Garrix - AMF.mkv"


def test_render_filename_missing_values_uses_fallbacks():
    mf = MediaFile(
        source_path=Path("mystery.mkv"),
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    # Should fall back to original filename when too much is missing
    assert result == "mystery.mkv"


def test_render_filename_edition_collapses_when_not_configured():
    """Edition for a festival without configured editions is omitted."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Martin Garrix",
        festival="AMF",
        year="2024",
        edition="Netherlands",
        extension=".mkv",
        content_type="festival_set",
    )
    result = render_filename(mf, CFG)
    assert result == "2024 - Martin Garrix - AMF.mkv"


# --- Filename rendering: concert films ---


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
    assert result == "Coldplay - A Head Full of Dreams (2018).mkv"


def test_render_filename_concert_no_year():
    """Concert film without year: year collapses cleanly."""
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="Michael Buble",
        title="Christmas Special",
        extension=".mkv",
        content_type="concert_film",
    )
    result = render_filename(mf, CFG)
    assert result == "Michael Buble - Christmas Special.mkv"


# --- _render() unit tests ---


def test_render_required_field_substitution():
    values = {"artist": "Hardwell", "year": "2025"}
    result = _render("{year} - {artist}", values, {})
    assert result == "2025 - Hardwell"


def test_render_optional_field_present():
    values = {"festival": "AMF", "stage": "Mainstage"}
    result = _render("{festival}{ [stage]}", values, {})
    assert result == "AMF [Mainstage]"


def test_render_optional_field_empty():
    values = {"festival": "AMF", "stage": ""}
    result = _render("{festival}{ [stage]}", values, {})
    assert result == "AMF"


def test_render_optional_separator_field_present():
    values = {"artist": "Hardwell", "set_title": "WE1"}
    result = _render("{artist}{ - set_title}", values, {})
    assert result == "Hardwell - WE1"


def test_render_optional_separator_field_empty():
    values = {"artist": "Hardwell", "set_title": ""}
    result = _render("{artist}{ - set_title}", values, {})
    assert result == "Hardwell"


def test_render_optional_parentheses_present():
    values = {"title": "A Head Full of Dreams", "year": "2018"}
    result = _render("{title}{ (year)}", values, {})
    assert result == "A Head Full of Dreams (2018)"


def test_render_optional_parentheses_empty():
    values = {"title": "Christmas Special", "year": ""}
    result = _render("{title}{ (year)}", values, {})
    assert result == "Christmas Special"


def test_render_fallback_for_required_field():
    values = {"artist": "", "year": "2025"}
    fallbacks = {"unknown_artist": "Unknown Artist"}
    result = _render("{year} - {artist}", values, fallbacks)
    assert result == "2025 - Unknown Artist"


def test_render_multiple_optional_fields_all_empty():
    values = {"festival": "AMF", "edition": "", "stage": "", "set_title": ""}
    result = _render("{festival}{ edition}{ [stage]}{ - set_title}", values, {})
    assert result == "AMF"


def test_render_multiple_optional_fields_all_present():
    values = {"festival": "Tomorrowland", "edition": "Belgium", "stage": "Mainstage", "set_title": "WE1"}
    result = _render("{festival}{ edition}{ [stage]}{ - set_title}", values, {})
    assert result == "Tomorrowland Belgium [Mainstage] - WE1"
