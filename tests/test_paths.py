"""Tests for festival_organizer.paths platform-path resolution."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from festival_organizer import paths


class TestDataDir:
    def test_windows_uses_documents_dir(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CRATEDIGGER_DATA_DIR", raising=False)
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch("festival_organizer.paths.platformdirs") as mock_pd:
            mock_sys.platform = "win32"
            mock_pd.user_documents_dir.return_value = "C:/Users/Name/Documents"
            result = paths.data_dir()
            assert result == Path("C:/Users/Name/Documents/CrateDigger")

    def test_non_windows_uses_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CRATEDIGGER_DATA_DIR", raising=False)
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch.object(Path, "home", return_value=tmp_path):
            mock_sys.platform = "linux"
            result = paths.data_dir()
            assert result == tmp_path / "CrateDigger"

    def test_darwin_uses_home_like_linux(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """macOS uses ~/CrateDigger/ (matches TrackSplit's ~/TrackSplit/ layout)."""
        monkeypatch.delenv("CRATEDIGGER_DATA_DIR", raising=False)
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch.object(Path, "home", return_value=tmp_path):
            mock_sys.platform = "darwin"
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

    def test_places_logo_dir(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.places_logo_dir() == tmp_path / "places"

    def test_places_file(self, tmp_path: Path):
        with patch("festival_organizer.paths.data_dir", return_value=tmp_path):
            assert paths.places_file() == tmp_path / "places.json"


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
        state = tmp_path / "state"
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        messages = [r.getMessage() for r in caplog.records if r.name == "festival_organizer.paths"]
        assert any(
            "legacy" in m.lower() or "old location" in m.lower()
            for m in messages
        )

    def test_silent_when_nothing_legacy(self, tmp_path: Path, caplog):
        state = tmp_path / "state"
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        ours = [r for r in caplog.records if r.name == "festival_organizer.paths"]
        assert ours == []


class TestWarnIfLegacyPathsExistDedup:
    """Stamp-file suppression: at most one legacy WARNING per day."""

    def _make_legacy(self, home: Path) -> Path:
        legacy = home / ".cratedigger"
        legacy.mkdir()
        (legacy / "config.json").write_text("{}")
        return legacy

    def _count_warnings(self, caplog) -> int:
        return sum(
            1 for r in caplog.records
            if r.name == "festival_organizer.paths" and r.levelname == "WARNING"
        )

    def test_first_call_warns_and_writes_stamp(self, tmp_path: Path, caplog):
        self._make_legacy(tmp_path)
        state = tmp_path / "state"
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        assert self._count_warnings(caplog) == 1
        stamp = state / "legacy-warning.stamp"
        assert stamp.is_file()
        assert stamp.read_text().strip() == date.today().isoformat()

    def test_second_call_same_day_silent(self, tmp_path: Path, caplog):
        self._make_legacy(tmp_path)
        state = tmp_path / "state"
        with patch("festival_organizer.paths.state_dir", return_value=state):
            with caplog.at_level("WARNING", logger="festival_organizer.paths"):
                paths.warn_if_legacy_paths_exist(home=tmp_path)
            caplog.clear()
            with caplog.at_level("WARNING", logger="festival_organizer.paths"):
                paths.warn_if_legacy_paths_exist(home=tmp_path)
        assert self._count_warnings(caplog) == 0

    def test_stale_stamp_triggers_rewarn(self, tmp_path: Path, caplog):
        self._make_legacy(tmp_path)
        state = tmp_path / "state"
        state.mkdir()
        stamp = state / "legacy-warning.stamp"
        stamp.write_text("2020-01-01")
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        assert self._count_warnings(caplog) == 1
        assert stamp.read_text().strip() == date.today().isoformat()

    def test_corrupt_stamp_recovers(self, tmp_path: Path, caplog):
        self._make_legacy(tmp_path)
        state = tmp_path / "state"
        state.mkdir()
        stamp = state / "legacy-warning.stamp"
        stamp.write_text("not a date, garbage \x00\x01")
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        assert self._count_warnings(caplog) == 1
        assert stamp.read_text().strip() == date.today().isoformat()

    def test_tomorrow_stamp_suppresses(self, tmp_path: Path, caplog):
        """A stamp dated in the future (clock skew, manual edit) still suppresses."""
        self._make_legacy(tmp_path)
        state = tmp_path / "state"
        state.mkdir()
        stamp = state / "legacy-warning.stamp"
        future = (date.today() + timedelta(days=1)).isoformat()
        stamp.write_text(future)
        with patch("festival_organizer.paths.state_dir", return_value=state), \
             caplog.at_level("WARNING", logger="festival_organizer.paths"):
            paths.warn_if_legacy_paths_exist(home=tmp_path)
        assert self._count_warnings(caplog) == 0


class TestIsSourceCheckoutDir:
    def test_matches_cratedigger_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "cratedigger"\nversion = "0.0.0"\n'
        )
        assert paths._is_source_checkout_dir(tmp_path) is True

    def test_case_insensitive(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "CrateDigger"\nversion = "0.0.0"\n'
        )
        assert paths._is_source_checkout_dir(tmp_path) is True

    def test_different_project_name(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "tracksplit"\nversion = "0.0.0"\n'
        )
        assert paths._is_source_checkout_dir(tmp_path) is False

    def test_no_pyproject(self, tmp_path: Path):
        assert paths._is_source_checkout_dir(tmp_path) is False

    def test_malformed_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("this is not toml =====")
        assert paths._is_source_checkout_dir(tmp_path) is False

    def test_pyproject_without_project_table(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "cratedigger"\n')
        assert paths._is_source_checkout_dir(tmp_path) is False

    def test_path_does_not_exist(self, tmp_path: Path):
        assert paths._is_source_checkout_dir(tmp_path / "nonexistent") is False


class TestWarnIfDataDirIsSourceCheckout:
    def _fake_source_checkout(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / "pyproject.toml").write_text(
            '[project]\nname = "cratedigger"\nversion = "0.0.0"\n'
        )
        return path

    @pytest.fixture(autouse=True)
    def _reset_warned_flag(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(paths, "_warned_source_checkout", False, raising=False)

    def test_warns_once_per_process(self, tmp_path: Path, caplog, monkeypatch):
        monkeypatch.delenv("CRATEDIGGER_DATA_DIR", raising=False)
        checkout = self._fake_source_checkout(tmp_path / "CrateDigger")
        with patch("festival_organizer.paths.data_dir", return_value=checkout):
            with caplog.at_level("WARNING", logger="festival_organizer.paths"):
                paths.warn_if_data_dir_is_source_checkout()
                paths.warn_if_data_dir_is_source_checkout()
                paths.warn_if_data_dir_is_source_checkout()
        warnings = [
            r for r in caplog.records
            if r.name == "festival_organizer.paths" and r.levelname == "WARNING"
        ]
        assert len(warnings) == 1
        assert "CRATEDIGGER_DATA_DIR" in warnings[0].getMessage()
        assert str(checkout) in warnings[0].getMessage()

    def test_silent_for_plain_dir(self, tmp_path: Path, caplog, monkeypatch):
        monkeypatch.delenv("CRATEDIGGER_DATA_DIR", raising=False)
        plain = tmp_path / "CrateDigger"
        plain.mkdir()
        with patch("festival_organizer.paths.data_dir", return_value=plain):
            with caplog.at_level("WARNING", logger="festival_organizer.paths"):
                paths.warn_if_data_dir_is_source_checkout()
        assert not any(
            r.name == "festival_organizer.paths" and r.levelname == "WARNING"
            for r in caplog.records
        )

    def test_silent_when_env_var_set(self, tmp_path: Path, caplog, monkeypatch):
        """If the user explicitly set CRATEDIGGER_DATA_DIR, they know what
        they're doing; don't nag even if the resolved dir is a source checkout."""
        checkout = self._fake_source_checkout(tmp_path / "CrateDigger")
        monkeypatch.setenv("CRATEDIGGER_DATA_DIR", str(checkout))
        with patch("festival_organizer.paths.data_dir", return_value=checkout):
            with caplog.at_level("WARNING", logger="festival_organizer.paths"):
                paths.warn_if_data_dir_is_source_checkout()
        assert not any(
            r.name == "festival_organizer.paths" and r.levelname == "WARNING"
            for r in caplog.records
        )

    def test_silent_when_data_dir_missing(self, tmp_path: Path, caplog, monkeypatch):
        monkeypatch.delenv("CRATEDIGGER_DATA_DIR", raising=False)
        ghost = tmp_path / "does-not-exist"
        with patch("festival_organizer.paths.data_dir", return_value=ghost):
            with caplog.at_level("WARNING", logger="festival_organizer.paths"):
                paths.warn_if_data_dir_is_source_checkout()
        assert not any(
            r.name == "festival_organizer.paths" and r.levelname == "WARNING"
            for r in caplog.records
        )


class TestDataDirEnvOverride:
    def test_env_var_wins_when_dir_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        custom = tmp_path / "custom"
        custom.mkdir()
        monkeypatch.setenv("CRATEDIGGER_DATA_DIR", str(custom))
        assert paths.data_dir() == custom

    def test_env_var_ignored_when_dir_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """If the env var points at a non-existent path, fall back to the
        platform default. Matches TrackSplit's behaviour so both tools agree."""
        ghost = tmp_path / "does_not_exist"
        monkeypatch.setenv("CRATEDIGGER_DATA_DIR", str(ghost))
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch.object(Path, "home", return_value=tmp_path):
            mock_sys.platform = "linux"
            assert paths.data_dir() == tmp_path / "CrateDigger"

    def test_env_var_ignored_when_dir_is_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Symmetric to TrackSplit: a file at the env var path is not a valid
        data dir, so fall back to the default."""
        blocker = tmp_path / "blocker"
        blocker.write_text("")
        monkeypatch.setenv("CRATEDIGGER_DATA_DIR", str(blocker))
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch.object(Path, "home", return_value=tmp_path):
            mock_sys.platform = "linux"
            assert paths.data_dir() == tmp_path / "CrateDigger"

    def test_empty_env_var_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CRATEDIGGER_DATA_DIR", "")
        with patch("festival_organizer.paths.sys") as mock_sys, \
             patch.object(Path, "home", return_value=tmp_path):
            mock_sys.platform = "linux"
            assert paths.data_dir() == tmp_path / "CrateDigger"


class TestMigrateLegacyPaths:
    """Auto-migration of festival-named curated paths to place-named locations."""

    def _wire(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        festivals_file: Path,
        places_file: Path,
        festivals_logo_dir: Path,
        places_logo_dir: Path,
    ) -> None:
        monkeypatch.setattr(paths, "festivals_file", lambda: festivals_file)
        monkeypatch.setattr(paths, "places_file", lambda: places_file)
        monkeypatch.setattr(paths, "festivals_logo_dir", lambda: festivals_logo_dir)
        monkeypatch.setattr(paths, "places_logo_dir", lambda: places_logo_dir)

    def test_copies_file_when_target_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        legacy = tmp_path / "festivals.json"
        legacy.write_text('{"X": {}}', encoding="utf-8")
        target = tmp_path / "places.json"
        self._wire(
            monkeypatch,
            festivals_file=legacy,
            places_file=target,
            festivals_logo_dir=tmp_path / "no_legacy_dir",
            places_logo_dir=tmp_path / "places_dir",
        )

        paths._migrate_legacy_paths()

        assert target.read_text(encoding="utf-8") == '{"X": {}}'
        assert legacy.exists(), "legacy festivals.json must be preserved"

    def test_skips_file_when_target_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        legacy = tmp_path / "festivals.json"
        legacy.write_text('{"old": {}}', encoding="utf-8")
        target = tmp_path / "places.json"
        target.write_text('{"new": {}}', encoding="utf-8")
        self._wire(
            monkeypatch,
            festivals_file=legacy,
            places_file=target,
            festivals_logo_dir=tmp_path / "no_legacy_dir",
            places_logo_dir=tmp_path / "places_dir",
        )

        paths._migrate_legacy_paths()

        assert target.read_text(encoding="utf-8") == '{"new": {}}'
        assert legacy.read_text(encoding="utf-8") == '{"old": {}}'

    def test_copies_logo_subdirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        legacy_dir = tmp_path / "festivals"
        (legacy_dir / "Tomorrowland").mkdir(parents=True)
        (legacy_dir / "Tomorrowland" / "logo.png").write_bytes(b"PNG")
        (legacy_dir / "Awakenings").mkdir()
        (legacy_dir / "Awakenings" / "logo.jpg").write_bytes(b"JPG")
        new_dir = tmp_path / "places"
        self._wire(
            monkeypatch,
            festivals_file=tmp_path / "no_legacy.json",
            places_file=tmp_path / "no_target.json",
            festivals_logo_dir=legacy_dir,
            places_logo_dir=new_dir,
        )

        paths._migrate_legacy_paths()

        assert (new_dir / "Tomorrowland" / "logo.png").read_bytes() == b"PNG"
        assert (new_dir / "Awakenings" / "logo.jpg").read_bytes() == b"JPG"
        assert (legacy_dir / "Tomorrowland" / "logo.png").exists()
        assert (legacy_dir / "Awakenings" / "logo.jpg").exists()

    def test_skips_existing_logo_subdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        legacy_dir = tmp_path / "festivals"
        (legacy_dir / "Tomorrowland").mkdir(parents=True)
        (legacy_dir / "Tomorrowland" / "logo.png").write_bytes(b"OLD")
        new_dir = tmp_path / "places"
        (new_dir / "Tomorrowland").mkdir(parents=True)
        (new_dir / "Tomorrowland" / "logo.png").write_bytes(b"NEW")
        self._wire(
            monkeypatch,
            festivals_file=tmp_path / "no_legacy.json",
            places_file=tmp_path / "no_target.json",
            festivals_logo_dir=legacy_dir,
            places_logo_dir=new_dir,
        )

        paths._migrate_legacy_paths()

        assert (new_dir / "Tomorrowland" / "logo.png").read_bytes() == b"NEW"

    def test_idempotent_within_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
    ):
        legacy = tmp_path / "festivals.json"
        legacy.write_text('{"X": {}}', encoding="utf-8")
        target = tmp_path / "places.json"
        legacy_dir = tmp_path / "festivals"
        (legacy_dir / "Tomorrowland").mkdir(parents=True)
        (legacy_dir / "Tomorrowland" / "logo.png").write_bytes(b"PNG")
        new_dir = tmp_path / "places"
        self._wire(
            monkeypatch,
            festivals_file=legacy,
            places_file=target,
            festivals_logo_dir=legacy_dir,
            places_logo_dir=new_dir,
        )

        with caplog.at_level(logging.INFO, logger="festival_organizer.paths"):
            paths._migrate_legacy_paths()
            paths._migrate_legacy_paths()
            paths._migrate_legacy_paths()

        info_records = [
            r for r in caplog.records
            if r.name == "festival_organizer.paths" and r.levelname == "INFO"
        ]
        file_msgs = [r for r in info_records if "places.json" in r.getMessage()]
        logo_msgs = [r for r in info_records if "Migrated curated logos" in r.getMessage()]
        assert len(file_msgs) == 1
        assert len(logo_msgs) == 1
