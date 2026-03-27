import json
import platform
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
