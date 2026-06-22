import json
import logging
import subprocess as subprocess_mod
from pathlib import Path
from unittest.mock import patch, MagicMock
from festival_organizer.metadata import (
    find_tool,
    get_install_hint,
)


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


def test_extract_ffprobe_new_tag_names():
    """ffprobe extraction reads new CRATEDIGGER_1001TL_* tags with old fallback."""
    from festival_organizer.metadata import _extract_ffprobe

    fake_output = json.dumps(
        {
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
        }
    )

    with patch("festival_organizer.metadata.FFPROBE_PATH", "/usr/bin/ffprobe"):
        with patch("festival_organizer.metadata.tracked_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            result = _extract_ffprobe(Path("/tmp/test.mkv"))

    assert result["tracklists_title"] == "New Title"
    assert result["tracklists_url"] == "https://new-url.com"
    assert result["tracklists_id"] == "abc123"
    assert result["tracklists_date"] == "2025-01-01"


def test_extract_ffprobe_old_tag_fallback():
    """ffprobe falls back to old 1001TRACKLISTS_* tags."""
    from festival_organizer.metadata import _extract_ffprobe

    fake_output = json.dumps(
        {
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
        }
    )

    with patch("festival_organizer.metadata.FFPROBE_PATH", "/usr/bin/ffprobe"):
        with patch("festival_organizer.metadata.tracked_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output)
            result = _extract_ffprobe(Path("/tmp/test.mkv"))

    assert result["tracklists_title"] == "Old Title"
    assert result["tracklists_url"] == "https://old-url.com"


# --- extract_metadata (ffprobe is the sole reader) ---


def test_extract_metadata_uses_ffprobe_only():
    """ffprobe is the sole reader: it reads MKV tags reliably regardless of where
    the Tags element sits in the file.

    Regression: MediaInfo's default partial parse can miss a Tags element
    positioned late in the file (after an mkvpropedit rewrite), silently dropping
    the CrateDigger tags and making an identified file look unidentified.
    """
    from festival_organizer.metadata import extract_metadata

    with patch(
        "festival_organizer.metadata._extract_ffprobe",
        return_value={"tracklists_url": "from_ffprobe"},
    ) as ff:
        result = extract_metadata(Path("/x/file.mkv"))
    assert result == {"tracklists_url": "from_ffprobe"}
    ff.assert_called_once()


def test_extract_metadata_warns_and_returns_empty_when_ffprobe_fails(caplog):
    from festival_organizer.metadata import extract_metadata

    with (
        caplog.at_level(logging.WARNING),
        patch("festival_organizer.metadata._extract_ffprobe", return_value={}),
    ):
        result = extract_metadata(Path("/x/file.mkv"))
    assert result == {}
    assert any("metadata" in r.message.lower() for r in caplog.records)
