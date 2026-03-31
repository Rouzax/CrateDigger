from pathlib import Path
from festival_organizer.parsers import (
    parse_1001tracklists_title,
    parse_filename,
    parse_parent_dirs,
)
from festival_organizer.config import Config
from tests.conftest import TEST_CONFIG


CFG = Config(TEST_CONFIG)


# --- 1001Tracklists title parser ---

def test_1001tl_basic_festival():
    result = parse_1001tracklists_title(
        "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, "
        "Amsterdam Dance Event, Netherlands 2024-10-19",
        CFG,
    )
    assert result["artist"] == "Martin Garrix"
    assert result["festival"] == "AMF"  # Alias resolved
    assert result["date"] == "2024-10-19"
    assert result["year"] == "2024"
    # Without a known location match, after-segments become location
    # (stage/venue split relies on structured tags from chapters command)
    assert "Johan Cruijff ArenA" in result.get("location", "")


def test_1001tl_tomorrowland_with_stage():
    result = parse_1001tracklists_title(
        "Hardwell @ The Great Library Stage, Tomorrowland Weekend 1, Belgium 2025-07-18",
        CFG,
    )
    assert result["artist"] == "Hardwell"
    assert result["festival"] == "Tomorrowland"
    assert result["location"] == "Belgium"
    assert result["year"] == "2025"
    assert result["stage"] == "The Great Library Stage"


def test_1001tl_ultra_with_parenthetical_artist():
    result = parse_1001tracklists_title(
        "Everything Always (Dom Dolla & John Summit) @ Mainstage, "
        "Ultra Music Festival Miami, United States 2025-03-28",
        CFG,
    )
    assert result["artist"] == "Everything Always (Dom Dolla & John Summit)"
    assert result["festival"] == "Ultra Music Festival"
    assert result["year"] == "2025"


def test_1001tl_b2b_at_venue():
    result = parse_1001tracklists_title(
        "Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24",
        CFG,
    )
    assert result["artist"] == "Martin Garrix & Alesso"
    assert result["festival"] == "Red Rocks"
    assert result["year"] == "2025"


def test_1001tl_edc():
    result = parse_1001tracklists_title(
        "Armin van Buuren @ kineticFIELD, EDC Las Vegas, United States 2025-05-18",
        CFG,
    )
    assert result["artist"] == "Armin van Buuren"
    assert result["festival"] == "EDC"
    assert result["stage"] == "kineticFIELD"


def test_1001tl_dreamstate_socal_location():
    """Location should come from festival alias, not country."""
    result = parse_1001tracklists_title(
        "Tiësto @ The Dream Stage, Dreamstate SoCal, "
        "Queen Mary Waterfront, United States 2025-11-22",
        CFG,
    )
    assert result["festival"] == "Dreamstate"
    assert result["location"] == "SoCal"
    assert "The Dream Stage" in result.get("stage", "")
    assert result["artist"] == "Tiësto"
    assert result["date"] == "2025-11-22"


def test_1001tl_edc_las_vegas_location():
    """EDC Las Vegas should extract Las Vegas as location."""
    result = parse_1001tracklists_title(
        "Armin van Buuren @ kineticFIELD, EDC Las Vegas, "
        "United States 2025-05-18",
        CFG,
    )
    assert result["festival"] == "EDC"
    assert result["location"] == "Las Vegas"
    assert result["stage"] == "kineticFIELD"


def test_1001tl_empty():
    assert parse_1001tracklists_title("", CFG) == {}
    assert parse_1001tracklists_title(None, CFG) == {}


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


def test_parent_dirs_tomorrowland_location():
    result = parse_parent_dirs(
        Path("//hyperv/Data/Concerts/Tomorrowland/2025 - Belgium/file.mkv"),
        Path("//hyperv/Data/Concerts"),
        CFG,
    )
    assert result.get("festival") == "Tomorrowland"
    assert result.get("location") == "Belgium"
    assert result.get("year") == "2025"


def test_parent_dirs_no_info():
    result = parse_parent_dirs(
        Path("/tmp/test/Downloads/random.mkv"),
        Path("/tmp/test/Downloads"),
        CFG,
    )
    assert result == {}
