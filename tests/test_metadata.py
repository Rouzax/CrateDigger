import json
import logging
import platform
import subprocess as subprocess_mod
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.metadata import (
    find_tool,
    get_install_hint,
    parse_mediainfo_json,
    extract_metadata,
)


def test_parse_mediainfo_json_full():
    """Test parsing a real MediaInfo JSON structure."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Title": "MARTIN GARRIX LIVE @ AMF 2024",
                    "Duration": "7200.000",
                    "OverallBitRate": "13500000",
                    "Format": "Matroska",
                    "Encoded_Date": "2025-03-15 09:20:31 UTC",
                    "ARTIST": "",
                    "DATE": "",
                    "Description": "",
                    "Comment": "",
                    "PURL": "",
                    "Attachments": "cover.png",
                    "extra": {
                        "_1001TRACKLISTS_TITLE": "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19",
                        "_1001TRACKLISTS_URL": "https://www.1001tracklists.com/tracklist/qv6kl89/",
                    },
                },
                {
                    "@type": "Video",
                    "Format": "VP9",
                    "Width": "3840",
                    "Height": "2160",
                    "BitRate": "13400000",
                    "FrameRate": "25.000",
                },
                {
                    "@type": "Audio",
                    "Format": "Opus",
                    "BitRate": "125000",
                    "Channels": "2",
                    "SamplingRate": "48000",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["title"] == "MARTIN GARRIX LIVE @ AMF 2024"
    assert meta["duration_seconds"] == 7200.0
    assert meta["tracklists_title"] == "Martin Garrix @ Amsterdam Music Festival, Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands 2024-10-19"
    assert meta["tracklists_url"] == "https://www.1001tracklists.com/tracklist/qv6kl89/"
    assert meta["width"] == 3840
    assert meta["height"] == 2160
    assert meta["video_format"] == "VP9"
    assert meta["audio_format"] == "Opus"
    assert meta["has_cover"] == True


def test_parse_mediainfo_json_minimal():
    """Test parsing MediaInfo JSON with minimal data (no extra tags)."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["title"] == ""
    assert meta["tracklists_title"] == ""
    assert meta["has_cover"] == False
    assert meta["duration_seconds"] == 3600.0


def test_parse_mediainfo_json_empty():
    meta = parse_mediainfo_json({})
    assert meta == {}
    meta2 = parse_mediainfo_json({"media": {"track": []}})
    assert meta2 == {}


def test_find_tool_in_path():
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        assert find_tool("mediainfo", []) == "/usr/bin/mediainfo"


def test_find_tool_fallback_paths(tmp_path):
    fake = tmp_path / "mediainfo"
    fake.write_text("fake")
    with patch("shutil.which", return_value=None):
        assert find_tool("mediainfo", [str(fake)]) == str(fake)


def test_find_tool_not_found():
    with patch("shutil.which", return_value=None):
        with patch("os.path.isfile", return_value=False):
            assert find_tool("mediainfo", []) is None


def test_find_tool_config_override(tmp_path):
    """Config-provided path takes priority over PATH."""
    custom = tmp_path / "custom_mediainfo"
    custom.write_text("fake")
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        result = find_tool("mediainfo", configured_path=str(custom))
    assert result == str(custom)


def test_find_tool_config_override_missing_falls_back(tmp_path):
    """Missing config override file falls back to PATH."""
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        result = find_tool("mediainfo", configured_path="/nonexistent/mediainfo")
    assert result == "/usr/bin/mediainfo"


def test_get_install_hint_macos():
    """macOS install hint uses brew."""
    with patch("platform.system", return_value="Darwin"):
        hint = get_install_hint("mediainfo")
    assert "brew install" in hint


def test_get_install_hint_linux():
    """Linux install hint uses apt."""
    with patch("platform.system", return_value="Linux"):
        hint = get_install_hint("mediainfo")
    assert "apt install" in hint


def test_get_install_hint_windows():
    """Windows install hint uses winget."""
    with patch("platform.system", return_value="Windows"):
        hint = get_install_hint("mediainfo")
    assert "winget install" in hint


def test_parse_mediainfo_json_new_tag_names():
    """New CRATEDIGGER_1001TL_* tags are read preferentially."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                    "CRATEDIGGER_1001TL_URL": "https://new-url.com",
                    "CRATEDIGGER_1001TL_TITLE": "New Title",
                    "CRATEDIGGER_1001TL_ID": "abc123",
                    "CRATEDIGGER_1001TL_DATE": "2025-01-01",
                    "CRATEDIGGER_1001TL_GENRES": "Trance|House",
                    "CRATEDIGGER_1001TL_EVENT_ARTWORK": "https://event.jpg",
                    "CRATEDIGGER_1001TL_DJ_ARTWORK": "https://dj.jpg",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["tracklists_url"] == "https://new-url.com"
    assert meta["tracklists_title"] == "New Title"
    assert meta["tracklists_id"] == "abc123"
    assert meta["tracklists_date"] == "2025-01-01"
    assert meta["tracklists_genres"] == "Trance|House"
    assert meta["tracklists_event_artwork"] == "https://event.jpg"
    assert meta["tracklists_dj_artwork"] == "https://dj.jpg"


def test_parse_mediainfo_json_old_tag_fallback():
    """Old 1001TRACKLISTS_* tags still work when new tags are absent."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                    "1001TRACKLISTS_URL": "https://old-url.com",
                    "1001TRACKLISTS_TITLE": "Old Title",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["tracklists_url"] == "https://old-url.com"
    assert meta["tracklists_title"] == "Old Title"


def test_parse_mediainfo_json_new_tag_preferred_over_old():
    """When both old and new tags exist, new tag wins."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                    "CRATEDIGGER_1001TL_URL": "https://new-url.com",
                    "1001TRACKLISTS_URL": "https://old-url.com",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["tracklists_url"] == "https://new-url.com"


def test_parse_mediainfo_json_enrichment_tags():
    """CRATEDIGGER_MBID etc. are read into metadata dict."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                    "CRATEDIGGER_MBID": "12345-abcde",
                    "CRATEDIGGER_FANART_URL": "https://fanart.tv/img.jpg",
                    "CRATEDIGGER_CLEARLOGO_URL": "https://fanart.tv/logo.png",
                    "CRATEDIGGER_ENRICHED_AT": "2025-06-01T12:00:00",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["mbid"] == "12345-abcde"
    assert meta["fanart_url"] == "https://fanart.tv/img.jpg"
    assert meta["clearlogo_url"] == "https://fanart.tv/logo.png"
    assert meta["enriched_at"] == "2025-06-01T12:00:00"


def test_parse_mediainfo_json_enrichment_tags_default_empty():
    """Enrichment tags default to empty string when absent."""
    raw = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "3600.0",
                    "Format": "Matroska",
                },
            ]
        }
    }
    meta = parse_mediainfo_json(raw)
    assert meta["mbid"] == ""
    assert meta["fanart_url"] == ""
    assert meta["clearlogo_url"] == ""
    assert meta["enriched_at"] == ""


def test_mediainfo_failure_is_logged(tmp_path, caplog):
    """When mediainfo subprocess fails, a debug message is logged."""
    from festival_organizer.metadata import _extract_mediainfo

    video = tmp_path / "test.mkv"
    video.write_bytes(b"")

    with patch("festival_organizer.metadata.MEDIAINFO_PATH", "/usr/bin/mediainfo"):
        with patch("festival_organizer.metadata.subprocess.run",
                   side_effect=subprocess_mod.SubprocessError("oops")):
            with caplog.at_level(logging.DEBUG, logger="festival_organizer.metadata"):
                result = _extract_mediainfo(video)
    assert result == {}
    assert "oops" in caplog.text


def test_extract_ffprobe_new_tag_names():
    """ffprobe extraction reads new CRATEDIGGER_1001TL_* tags with old fallback."""
    from festival_organizer.metadata import _extract_ffprobe

    fake_output = json.dumps({
        "format": {
            "duration": "3600.0",
            "bit_rate": "13500000",
            "format_long_name": "Matroska",
            "tags": {
                "CRATEDIGGER_1001TL_TITLE": "New Title",
                "CRATEDIGGER_1001TL_URL": "https://new-url.com",
                "CRATEDIGGER_1001TL_ID": "abc123",
                "CRATEDIGGER_1001TL_DATE": "2025-01-01",
            },
        },
        "streams": [],
    })

    with patch("festival_organizer.metadata.FFPROBE_PATH", "/usr/bin/ffprobe"):
        with patch("festival_organizer.metadata.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            result = _extract_ffprobe(Path("/tmp/test.mkv"))

    assert result["tracklists_title"] == "New Title"
    assert result["tracklists_url"] == "https://new-url.com"
    assert result["tracklists_id"] == "abc123"
    assert result["tracklists_date"] == "2025-01-01"


def test_extract_ffprobe_old_tag_fallback():
    """ffprobe falls back to old 1001TRACKLISTS_* tags."""
    from festival_organizer.metadata import _extract_ffprobe

    fake_output = json.dumps({
        "format": {
            "duration": "3600.0",
            "bit_rate": "13500000",
            "format_long_name": "Matroska",
            "tags": {
                "1001TRACKLISTS_TITLE": "Old Title",
                "1001TRACKLISTS_URL": "https://old-url.com",
            },
        },
        "streams": [],
    })

    with patch("festival_organizer.metadata.FFPROBE_PATH", "/usr/bin/ffprobe"):
        with patch("festival_organizer.metadata.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            result = _extract_ffprobe(Path("/tmp/test.mkv"))

    assert result["tracklists_title"] == "Old Title"
    assert result["tracklists_url"] == "https://old-url.com"
