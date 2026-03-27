import json
from pathlib import Path
from festival_organizer.library import find_library_root, init_library


def test_find_library_root_at_path(tmp_path):
    """Find .cratedigger/ marker at the given path."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    assert find_library_root(tmp_path) == tmp_path


def test_find_library_root_walks_up(tmp_path):
    """Walk up from subfolder to find .cratedigger/ marker."""
    marker = tmp_path / ".cratedigger"
    marker.mkdir()
    sub = tmp_path / "Artist" / "Festival"
    sub.mkdir(parents=True)
    assert find_library_root(sub) == tmp_path


def test_find_library_root_returns_none(tmp_path):
    """Return None when no marker found."""
    sub = tmp_path / "some" / "deep" / "path"
    sub.mkdir(parents=True)
    assert find_library_root(sub) is None


def test_find_library_root_stops_at_filesystem_root(tmp_path):
    """Don't walk above filesystem boundaries."""
    result = find_library_root(tmp_path)
    assert result is None


def test_init_library_creates_marker(tmp_path):
    """init_library creates .cratedigger/ directory."""
    init_library(tmp_path)
    assert (tmp_path / ".cratedigger").is_dir()


def test_init_library_creates_config(tmp_path):
    """init_library creates config.json with layout."""
    init_library(tmp_path, layout="festival_flat")
    cfg = json.loads((tmp_path / ".cratedigger" / "config.json").read_text())
    assert cfg["default_layout"] == "festival_flat"


def test_init_library_idempotent(tmp_path):
    """Running init_library twice doesn't overwrite existing config."""
    init_library(tmp_path, layout="festival_flat")
    # Manually add a custom setting
    cfg_path = tmp_path / ".cratedigger" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["custom_key"] = "custom_value"
    cfg_path.write_text(json.dumps(cfg))
    # Re-init should not clobber
    init_library(tmp_path, layout="artist_flat")
    cfg = json.loads(cfg_path.read_text())
    assert cfg["custom_key"] == "custom_value"


def test_find_library_root_config_dir(tmp_path):
    """find_library_root returns path from real subfolder."""
    init_library(tmp_path, layout="artist_nested")
    # From a real subfolder:
    sub = tmp_path / "Artist"
    sub.mkdir()
    root = find_library_root(sub)
    assert root == tmp_path
