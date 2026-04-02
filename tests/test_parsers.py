from pathlib import Path
from festival_organizer.parsers import (
    parse_filename,
    parse_parent_dirs,
)
from festival_organizer.config import Config
from tests.conftest import TEST_CONFIG


CFG = Config(TEST_CONFIG)


# --- Filename parser ---

def test_filename_yyyy_festival_artist():
    result = parse_filename(Path("2025 - AMF - Armin van Buuren.mkv"), CFG)
    assert result["year"] == "2025"
    assert result["festival"] == "AMF"
    assert result["artist"] == "Armin van Buuren"


def test_filename_yyyy_festival_artist_weekend():
    result = parse_filename(Path("2025 - Belgium - Hardwell WE1.mkv"), CFG)
    assert result["year"] == "2025"
    assert result["artist"] == "Hardwell"
    assert result["set_title"] == "WE1"


def test_filename_artist_live_at_festival():
    result = parse_filename(Path("MARTIN GARRIX LIVE @ AMF 2024.mkv"), CFG)
    assert result["artist"] == "MARTIN GARRIX"
    assert result["year"] == "2024"


def test_filename_artist_at_festival():
    result = parse_filename(
        Path("Armin van Buuren live at EDC Las Vegas 2025 [Dp7AwrAKckQ].mkv"), CFG
    )
    assert result["artist"] == "Armin van Buuren"
    assert result["year"] == "2025"
    assert result["youtube_id"] == "Dp7AwrAKckQ"


def test_filename_artist_dash_title():
    result = parse_filename(Path("Tiësto - AMF 2024 (Live Set) [fgipozjOI10].mkv"), CFG)
    assert result["youtube_id"] == "fgipozjOI10"
    assert "Tiësto" in result.get("artist", "")


def test_filename_scene_style():
    result = parse_filename(
        Path("glastonbury.2016.coldplay.1080p.hdtv.x264-verum.mkv"), CFG
    )
    assert result["year"] == "2016"
    # Should detect glastonbury as festival
    assert "glastonbury" in result.get("festival", "").lower() or "Glastonbury" in result.get("festival", "")


def test_filename_concert_style():
    result = parse_filename(Path("Adele - Live At The Royal Albert Hall-concert.mkv"), CFG)
    assert "Adele" in result.get("artist", "")


def test_filename_complex_youtube():
    result = parse_filename(
        Path("Everything Always (Dom Dolla & John Summit) Live @ Ultra Music Festival 2025 [9ZqJPIbTme4].mkv"),
        CFG,
    )
    assert result["youtube_id"] == "9ZqJPIbTme4"
    assert result["year"] == "2025"


# --- Parent directory parser ---

def test_parent_dirs_festival_year():
    result = parse_parent_dirs(
        Path("//hyperv/Data/Concerts/AMF/2024 - AMF/file.mkv"),
        Path("//hyperv/Data/Concerts"),
        CFG,
    )
    assert result.get("year") == "2024"
    assert result.get("festival") == "AMF"


def test_parent_dirs_tomorrowland_edition():
    result = parse_parent_dirs(
        Path("//hyperv/Data/Concerts/Tomorrowland/2025 - Winter/file.mkv"),
        Path("//hyperv/Data/Concerts"),
        CFG,
    )
    assert result.get("festival") == "Tomorrowland"
    assert result.get("edition") == "Winter"
    assert result.get("year") == "2025"


def test_parent_dirs_no_info():
    result = parse_parent_dirs(
        Path("/tmp/test/Downloads/random.mkv"),
        Path("/tmp/test/Downloads"),
        CFG,
    )
    assert result == {}
