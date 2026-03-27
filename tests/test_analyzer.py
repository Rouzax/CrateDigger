from pathlib import Path
from unittest.mock import patch
from festival_organizer.analyzer import analyse_file
from festival_organizer.config import Config, DEFAULT_CONFIG
from festival_organizer.models import MediaFile

CFG = Config(DEFAULT_CONFIG)


def test_analyse_with_1001tl_overrides_filename():
    """1001TL data should take priority over filename parsing."""
    fake_meta = {
        "title": "MARTIN GARRIX LIVE @ AMF 2024",
        "tracklists_title": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/qv6kl89/",
        "duration_seconds": 7200.0,
        "width": 3840,
        "height": 2160,
        "video_format": "VP9",
        "audio_format": "Opus",
        "audio_bitrate": "125000",
        "overall_bitrate": "13500000",
        "has_cover": True,
        "artist_tag": "",
        "date_tag": "",
        "description": "",
        "comment": "",
        "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/AMF/2024 - AMF/MARTIN GARRIX LIVE @ AMF 2024.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert isinstance(mf, MediaFile)
    assert mf.artist == "Martin Garrix"
    assert mf.festival == "AMF"
    assert mf.year == "2024"
    assert mf.date == "2024-10-19"
    assert mf.metadata_source == "1001tracklists"
    assert mf.has_cover == True


def test_analyse_filename_only():
    """When no metadata is available, filename parsing should work."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/AMF/2025 - AMF/2025 - AMF - Armin van Buuren.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert mf.artist == "Armin van Buuren"
    assert mf.festival == "AMF"
    assert mf.year == "2025"
    assert mf.metadata_source == "filename"


def test_analyse_concert_film():
    """Concert films with minimal metadata."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/Adele/2011 - Live/Adele - Live At The Royal Albert Hall-concert.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert "Adele" in mf.artist
    assert mf.year == "2011"


def test_analyse_embedded_artist_tag():
    """ARTIST metadata tag should fill in if filename doesn't provide it."""
    fake_meta = {
        "title": "",
        "tracklists_title": "",
        "tracklists_url": "",
        "artist_tag": "Michael Bublé",
        "date_tag": "20171215",
        "duration_seconds": 3900.0,
        "width": 3840,
        "height": 2160,
        "video_format": "VP9",
        "audio_format": "Opus",
        "audio_bitrate": "",
        "overall_bitrate": "",
        "has_cover": True,
        "description": "",
        "comment": "",
        "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/Michael Buble/some file.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert mf.artist == "Michael Bublé"
    assert mf.year == "2017"
