"""Tests for festival_organizer.paths platform-path resolution."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from festival_organizer import paths


class TestDataDir:
    def test_windows_uses_documents_dir(self):
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch("festival_organizer.paths.platformdirs") as mock_pd:
            mock_sys.platform = "win32"
            mock_pd.user_documents_dir.return_value = "C:/Users/Name/Documents"
            result = paths.data_dir()
            assert result == Path("C:/Users/Name/Documents/CrateDigger")

    def test_non_windows_uses_home(self, tmp_path: Path):
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch.object(Path, "home", return_value=tmp_path):
            mock_sys.platform = "linux"
            result = paths.data_dir()
            assert result == tmp_path / "CrateDigger"


class TestConfigFile:
    def test_config_lives_in_data_dir(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.config_file() == tmp_path / "config.toml"


class TestCacheDir:
    def test_uses_platformdirs_user_cache_dir(self):
        with patch("festival_organizer.paths.platformdirs") as mock_pd:
            mock_pd.user_cache_dir.return_value = "/fake/cache/CrateDigger"
            result = paths.cache_dir()
            mock_pd.user_cache_dir.assert_called_once_with("CrateDigger", appauthor=False)
            assert result == Path("/fake/cache/CrateDigger")


class TestStateDir:
    def test_uses_platformdirs_user_state_dir(self):
        with patch("festival_organizer.paths.platformdirs") as mock_pd:
            mock_pd.user_state_dir.return_value = "/fake/state/CrateDigger"
            result = paths.state_dir()
            mock_pd.user_state_dir.assert_called_once_with("CrateDigger", appauthor=False)
            assert result == Path("/fake/state/CrateDigger")


class TestConfigPathIsInsideDataDir:
    """Smoke check: config_file() and festivals_file() share the same parent."""

    def test_config_and_curated_share_parent(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.config_file().parent == paths.festivals_file().parent == tmp_path


class TestLogFile:
    def test_uses_platformdirs_user_log_dir(self):
        with patch("festival_organizer.paths.platformdirs") as mock_pd:
            mock_pd.user_log_dir.return_value = "/fake/log/CrateDigger"
            result = paths.log_file()
            mock_pd.user_log_dir.assert_called_once_with("CrateDigger", appauthor=False)
            assert result == Path("/fake/log/CrateDigger/cratedigger.log")


class TestCuratedDataFiles:
    def test_festivals_file(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.festivals_file() == tmp_path / "festivals.json"

    def test_artists_file(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.artists_file() == tmp_path / "artists.json"

    def test_artist_mbids_file(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.artist_mbids_file() == tmp_path / "artist_mbids.json"

    def test_festivals_logo_dir(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.festivals_logo_dir() == tmp_path / "festivals"


class TestCookiesFile:
    def test_lives_in_state_dir(self, tmp_path: Path):
        with patch("festival_organizer.paths.state_dir", return_value=tmp_path):
            assert paths.cookies_file() == tmp_path / "1001tl-cookies.json"


class TestArtistCacheDir:
    def test_per_artist_subfolder(self, tmp_path: Path):
        with patch("festival_organizer.paths.cache_dir", return_value=tmp_path):
            result = paths.artist_cache_dir("tiesto")
            assert result == tmp_path / "artists" / "tiesto"

    def test_sanitizes_tricky_artist_names(self, tmp_path: Path):
        with patch("festival_organizer.paths.cache_dir", return_value=tmp_path):
            result = paths.artist_cache_dir("AC/DC: The Band")
            # No path separators leaking; parent dir is "artists"
            assert result.parent == tmp_path / "artists"
            assert "/" not in result.name and "\\" not in result.name


class TestEnsureParent:
    def test_creates_missing_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "a" / "b" / "c" / "file.txt"
        result = paths.ensure_parent(target)
        assert target.parent.is_dir()
        assert result == target

    def test_idempotent(self, tmp_path: Path):
        target = tmp_path / "file.txt"
        paths.ensure_parent(target)
        paths.ensure_parent(target)
        assert tmp_path.is_dir()


class TestLegacyPathDetection:
    def test_detects_legacy_cratedigger_home(self, tmp_path: Path):
        legacy = tmp_path / ".cratedigger"
        legacy.mkdir()
        (legacy / "config.json").write_text("{}")
        found = paths._legacy_paths_present(home=tmp_path)
        assert legacy in found

    def test_detects_rogue_cookies(self, tmp_path: Path):
        rogue = tmp_path / ".1001tl-cookies.json"
        rogue.write_text("{}")
        found = paths._legacy_paths_present(home=tmp_path)
        assert rogue in found

    def test_empty_when_nothing_legacy(self, tmp_path: Path):
        assert paths._legacy_paths_present(home=tmp_path) == []


class TestWarnIfLegacyPathsExist:
    def test_warns_once_when_legacy_present(self, tmp_path: Path, caplog):
        legacy = tmp_path / ".cratedigger"
        legacy.mkdir()
        (legacy / "config.json").write_text("{}")
        with caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        messages = [r.getMessage() for r in caplog.records if r.name == "festival_organizer.paths"]
        assert any(
            "legacy" in m.lower() or "old location" in m.lower()
            for m in messages
        )

    def test_silent_when_nothing_legacy(self, tmp_path: Path, caplog):
        with caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        ours = [r for r in caplog.records if r.name == "festival_organizer.paths"]
        assert ours == []
