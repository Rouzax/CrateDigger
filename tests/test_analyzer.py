from pathlib import Path
from unittest.mock import patch
from festival_organizer.analyzer import analyse_file
from festival_organizer.config import Config
from festival_organizer.models import MediaFile
from tests.conftest import TEST_CONFIG

CFG = Config(TEST_CONFIG)


def test_analyse_with_1001tl_overrides_filename():
    """1001TL dedicated tags should take priority over filename parsing."""
    fake_meta = {
        "title": "MARTIN GARRIX LIVE @ AMF 2024",
        "tracklists_title": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/qv6kl89/",
        "tracklists_artists": "Martin Garrix",
        "tracklists_festival": "Amsterdam Music Festival",
        "tracklists_date": "2024-10-19",
        "tracklists_venue": "Johan Cruijff ArenA",
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


def test_analyse_maps_enrichment_fields():
    """Enrichment fields (mbid, fanart_url, etc.) are mapped from metadata."""
    fake_meta = {
        "title": "",
        "tracklists_title": "",
        "tracklists_url": "",
        "artist_tag": "Test",
        "date_tag": "",
        "mbid": "abc-123",
        "fanart_url": "https://fanart.tv/bg.jpg",
        "clearlogo_url": "https://fanart.tv/logo.png",
        "enriched_at": "2026-03-30T12:00:00",
        "duration_seconds": None,
        "width": None,
        "height": None,
        "video_format": "",
        "audio_format": "",
        "audio_bitrate": "",
        "overall_bitrate": "",
        "has_cover": False,
        "description": "",
        "comment": "",
        "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(Path("/tmp/test/file.mkv"), Path("/tmp/test"), CFG)
    assert mf.mbid == "abc-123"
    assert mf.fanart_url == "https://fanart.tv/bg.jpg"
    assert mf.clearlogo_url == "https://fanart.tv/logo.png"
    assert mf.enriched_at == "2026-03-30T12:00:00"


def test_analyse_enrichment_fields_default_empty():
    """Enrichment fields default to empty when not in metadata."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(Path("/tmp/test/file.mkv"), Path("/tmp/test"), CFG)
    assert mf.mbid == ""
    assert mf.fanart_url == ""
    assert mf.clearlogo_url == ""
    assert mf.enriched_at == ""


def test_display_artist_from_1001tl_b2b():
    """display_artist preserves full B2B name from 1001TL artists tag."""
    fake_meta = {
        "title": "MARTIN GARRIX B2B ALESSO LIVE @ RED ROCKS 2025",
        "tracklists_title": "Martin Garrix & Alesso @ Red Rocks Amphitheatre, United States 2025-10-24",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/20uhfc4k/",
        "tracklists_artists": "Martin Garrix|Alesso",
        "artist_tag": "Martin Garrix, Alesso",
        "date_tag": "",
        "duration_seconds": 3600.0, "width": 1920, "height": 1080,
        "video_format": "VP9", "audio_format": "Opus",
        "audio_bitrate": "", "overall_bitrate": "",
        "has_cover": True, "description": "", "comment": "", "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("D:/TEMP/_ORG/MARTIN GARRIX B2B ALESSO LIVE @ RED ROCKS 2025 [J8P_X7Fc5as].mkv"),
            Path("D:/TEMP/_ORG"),
            CFG,
        )
    assert mf.artist == "Martin Garrix"  # primary for folders
    assert mf.display_artist == "Martin Garrix & Alesso"  # full for filenames


def test_display_artist_solo_matches_artist():
    """For solo artists, display_artist equals artist."""
    fake_meta = {
        "title": "MARTIN GARRIX LIVE @ AMF 2024",
        "tracklists_title": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
        "tracklists_url": "https://www.1001tracklists.com/tracklist/qv6kl89/",
        "tracklists_artists": "Martin Garrix",
        "artist_tag": "",
        "date_tag": "",
        "duration_seconds": 7200.0, "width": 3840, "height": 2160,
        "video_format": "VP9", "audio_format": "Opus",
        "audio_bitrate": "125000", "overall_bitrate": "13500000",
        "has_cover": True, "description": "", "comment": "", "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("//hyperv/Data/Concerts/AMF/2024 - AMF/MARTIN GARRIX LIVE @ AMF 2024.mkv"),
            Path("//hyperv/Data/Concerts"),
            CFG,
        )
    assert mf.artist == "Martin Garrix"
    assert mf.display_artist == "Martin Garrix"


def test_display_artist_ignores_artist_tag():
    """display_artist is NOT derived from ARTIST tag (which stores primary only)."""
    fake_meta = {
        "title": "", "tracklists_title": "", "tracklists_url": "",
        "artist_tag": "Martin Garrix",
        "date_tag": "", "duration_seconds": None,
        "width": None, "height": None,
        "video_format": "", "audio_format": "",
        "audio_bitrate": "", "overall_bitrate": "",
        "has_cover": False, "description": "", "comment": "", "purl": "",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/Martin Garrix/2025 - Red Rocks - Martin Garrix & Alesso.mkv"),
            Path("/library"),
            CFG,
        )
    # Filename gives "Martin Garrix & Alesso", ARTIST tag gives "Martin Garrix"
    # display_artist should come from filename (skip ARTIST tag)
    assert mf.display_artist == "Martin Garrix & Alesso"
    assert mf.artist == "Martin Garrix"  # resolved primary


def test_display_artist_filename_only_b2b():
    """display_artist works from filename alone (no tags)."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("/downloads/MARTIN GARRIX B2B ALESSO LIVE @ RED ROCKS 2025.mkv"),
            Path("/downloads"),
            CFG,
        )
    assert mf.display_artist == "Martin Garrix B2B Alesso"
    # artist is the primary (first) from B2B split; stays uppercase without alias match
    assert mf.artist == "MARTIN GARRIX"


def test_analyzer_artists_tag_collab():
    """tracklists_artists with 2 entries splits into artist + display_artist."""
    fake_meta = {
        "tracklists_artists": "Armin van Buuren|KI/KI",
        "tracklists_festival": "Tomorrowland",
        "tracklists_date": "2025-07-18",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/2025 - Tomorrowland - Armin van Buuren.mkv"),
            Path("/library"),
            CFG,
        )
    assert mf.artist == "Armin van Buuren"
    assert mf.display_artist == "Armin van Buuren & KI/KI"


def test_analyzer_artists_tag_solo():
    """tracklists_artists with 1 entry uses same for artist and display_artist."""
    fake_meta = {
        "tracklists_artists": "Dimitri Vegas & Like Mike",
        "tracklists_festival": "Tomorrowland",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/2025 - Tomorrowland - DVLM.mkv"),
            Path("/library"),
            CFG,
        )
    assert mf.artist == "Dimitri Vegas & Like Mike"
    assert mf.display_artist == "Dimitri Vegas & Like Mike"


def test_display_artist_group_with_members():
    """display_artist enriched from 1001TL title for group acts with members."""
    fake_meta = {
        "tracklists_artists": "Everything Always",
        "tracklists_title": "Everything Always (Dom Dolla & John Summit) @ Mainstage, Ultra Music Festival Miami, United States 2025-03-28",
        "tracklists_festival": "Ultra Music Festival Miami",
        "tracklists_date": "2025-03-28",
        "tracklists_stage": "Mainstage",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/UMF Miami/2025 - Everything Always (Dom Dolla & John Summit) - UMF Miami [Mainstage].mkv"),
            Path("/library"),
            CFG,
        )
    assert mf.artist == "Everything Always"
    assert mf.display_artist == "Everything Always (Dom Dolla & John Summit)"


def test_analyzer_no_artists_tag_falls_back():
    """Without tracklists_artists, falls back to filename parsing."""
    with patch("festival_organizer.analyzer.extract_metadata", return_value={}):
        mf = analyse_file(
            Path("/library/2025 - AMF - Armin van Buuren.mkv"),
            Path("/library"),
            CFG,
        )
    assert mf.artist == "Armin van Buuren"
    assert mf.metadata_source == "filename"


def test_analyzer_edition_empty_for_amf():
    """AMF with venue/conference in title should NOT produce edition."""
    fake_meta = {
        "tracklists_festival": "Amsterdam Music Festival",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/2024 - AMF - Martin Garrix.mkv"),
            Path("/library"),
            CFG,
        )
    assert mf.edition == ""


def test_analyzer_tracklists_date_overwrites():
    """tracklists_date should overwrite date and year."""
    fake_meta = {
        "tracklists_artists": "Hardwell",
        "tracklists_date": "2025-10-25",
    }
    with patch("festival_organizer.analyzer.extract_metadata", return_value=fake_meta):
        mf = analyse_file(
            Path("/library/2024 - AMF - Hardwell.mkv"),
            Path("/library"),
            CFG,
        )
    assert mf.date == "2025-10-25"
    assert mf.year == "2025"
