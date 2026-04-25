"""Unit tests for festival_organizer.update_check. No real HTTP is performed."""
from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from festival_organizer.update_check import (
    SCHEMA_VERSION,
    _cache_is_fresh,
    _cache_path,
    _is_newer,
    _is_prerelease_string,
    _read_cache,
    _write_cache,
)


@pytest.fixture
def mock_paths(tmp_path):
    """Patch festival_organizer.update_check.paths so cache_dir resolves to tmp_path."""
    with patch("festival_organizer.update_check.paths") as m:
        m.cache_dir.return_value = tmp_path
        m.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        yield m


def test_module_imports():
    from festival_organizer import update_check
    assert update_check.PACKAGE_NAME == "cratedigger"
    assert update_check.ENV_VAR == "CRATEDIGGER_NO_UPDATE_CHECK"


class TestIsNewer:
    def test_patch_bump(self):
        assert _is_newer(installed="0.6.7", candidate="0.6.8")

    def test_minor_bump(self):
        assert _is_newer(installed="0.6.7", candidate="0.7.0")

    def test_major_bump(self):
        assert _is_newer(installed="0.6.7", candidate="1.0.0")

    def test_equal(self):
        assert not _is_newer(installed="0.6.7", candidate="0.6.7")

    def test_older(self):
        assert not _is_newer(installed="0.6.7", candidate="0.6.6")

    def test_numeric_not_lexicographic(self):
        assert _is_newer(installed="0.6.7", candidate="0.6.10")
        assert _is_newer(installed="0.9.0", candidate="0.10.0")

    def test_malformed_returns_false(self):
        assert not _is_newer(installed="0.6.7", candidate="weird")
        assert not _is_newer(installed="weird", candidate="0.6.7")


class TestIsPrereleaseString:
    @pytest.mark.parametrize("v", ["0.7.0rc1", "0.7.0a1", "0.7.0b2",
                                   "0.7.0.dev1", "0.7.0-rc.1", "0.7.0.post1"])
    def test_prerelease(self, v):
        assert _is_prerelease_string(v)

    @pytest.mark.parametrize("v", ["0.7.0", "1.0.0", "0.6.7"])
    def test_stable(self, v):
        assert not _is_prerelease_string(v)


class TestCachePath:
    def test_returns_cache_dir_joined_with_filename(self, tmp_path, mock_paths):
        assert _cache_path() == tmp_path / "update-check.json"


class TestReadWriteCache:
    def test_write_then_read(self, tmp_path, mock_paths):
        _write_cache(latest_version="0.7.0", ttl_seconds=86400)
        entry = _read_cache()
        assert entry is not None
        assert entry["latest_version"] == "0.7.0"
        assert entry["ttl_seconds"] == 86400
        assert entry["schema"] == SCHEMA_VERSION
        assert "checked_at" in entry

    def test_read_missing_returns_none(self, tmp_path, mock_paths):
        assert _read_cache() is None

    def test_read_corrupt_returns_none(self, tmp_path, mock_paths):
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not json {{{")
        assert _read_cache() is None

    def test_read_unknown_schema_returns_none(self, tmp_path, mock_paths):
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"schema": 999, "latest_version": "0.7.0"}))
        assert _read_cache() is None

    def test_write_is_atomic(self, tmp_path, mock_paths):
        """_write_cache must write to a temp file and rename; a crash mid-write
        must never leave the final file in a corrupted state."""
        _write_cache(latest_version="0.7.0", ttl_seconds=86400)
        p = _cache_path()
        assert p.exists()
        leftovers = [x for x in p.parent.iterdir() if x.name != p.name]
        assert leftovers == []


class TestCacheIsFresh:
    def test_fresh_recent(self):
        entry = {"checked_at": int(time.time()) - 1000, "ttl_seconds": 86400}
        assert _cache_is_fresh(entry)

    def test_stale_expired(self):
        entry = {"checked_at": int(time.time()) - 100_000, "ttl_seconds": 86400}
        assert not _cache_is_fresh(entry)

    def test_missing_fields_not_fresh(self):
        assert not _cache_is_fresh({"ttl_seconds": 86400})
        assert not _cache_is_fresh({"checked_at": 0})
        assert not _cache_is_fresh({})


class TestFetchLatestRelease:
    def _fake_response(self, body: bytes):
        from io import BytesIO
        r = BytesIO(body)
        return r

    def test_success(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        payload = b'{"tag_name": "v0.7.0"}'
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(payload)):
            assert _fetch_latest_release() == "0.7.0"

    def test_strips_single_leading_v(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        payload = b'{"tag_name": "v1.0.0"}'
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(payload)):
            assert _fetch_latest_release() == "1.0.0"

    def test_no_leading_v(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        payload = b'{"tag_name": "0.7.0"}'
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(payload)):
            assert _fetch_latest_release() == "0.7.0"

    def test_timeout_returns_none(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        with patch("festival_organizer.update_check.urlopen", side_effect=TimeoutError()):
            assert _fetch_latest_release() is None

    def test_url_error_returns_none(self):
        from unittest.mock import patch
        from urllib.error import URLError

        from festival_organizer.update_check import _fetch_latest_release
        with patch("festival_organizer.update_check.urlopen", side_effect=URLError("dns")):
            assert _fetch_latest_release() is None

    def test_http_error_returns_none(self):
        from unittest.mock import patch
        from urllib.error import HTTPError

        from festival_organizer.update_check import _fetch_latest_release
        err = HTTPError("u", 500, "boom", {}, None)  # type: ignore[arg-type]
        with patch("festival_organizer.update_check.urlopen", side_effect=err):
            assert _fetch_latest_release() is None

    def test_malformed_json_returns_none(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(b"not json")):
            assert _fetch_latest_release() is None

    def test_missing_tag_returns_none(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(b"{}")):
            assert _fetch_latest_release() is None

    def test_prerelease_returns_none(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        payload = b'{"tag_name": "v0.7.0rc1"}'
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(payload)):
            assert _fetch_latest_release() is None

    def test_malformed_tag_returns_none(self):
        from unittest.mock import patch

        from festival_organizer.update_check import _fetch_latest_release
        payload = b'{"tag_name": "bogus"}'
        with patch("festival_organizer.update_check.urlopen", return_value=self._fake_response(payload)):
            assert _fetch_latest_release() is None


class TestIsSuppressed:
    def test_not_suppressed_default(self, monkeypatch):
        from festival_organizer.update_check import _is_suppressed
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert not _is_suppressed()

    def test_suppressed_when_not_tty(self, monkeypatch):
        from festival_organizer.update_check import _is_suppressed
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        assert _is_suppressed()

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
    def test_env_var_truthy(self, monkeypatch, value):
        from festival_organizer.update_check import _is_suppressed
        monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", value)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert _is_suppressed()

    @pytest.mark.parametrize("value", ["0", "false", "no", ""])
    def test_env_var_falsy(self, monkeypatch, value):
        from festival_organizer.update_check import _is_suppressed
        monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", value)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        assert not _is_suppressed()


class TestUpgradeCommand:
    def test_pipx_via_env(self, monkeypatch):
        from festival_organizer.update_check import _upgrade_command
        monkeypatch.setenv("PIPX_HOME", "/home/user/.local/pipx")
        monkeypatch.setattr("sys.prefix", "/usr/lib/python3.11")
        assert "pipx upgrade cratedigger" in _upgrade_command()

    def test_pipx_via_prefix(self, monkeypatch):
        from festival_organizer.update_check import _upgrade_command
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.setattr("sys.prefix", "/home/user/.local/pipx/venvs/cratedigger")
        assert "pipx upgrade cratedigger" in _upgrade_command()

    def test_uv_tool(self, monkeypatch):
        from festival_organizer.update_check import _upgrade_command
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.setattr("sys.prefix", "/home/user/.local/share/uv/tools/cratedigger")
        assert "uv tool upgrade cratedigger" in _upgrade_command()

    def test_default_pip(self, monkeypatch):
        from festival_organizer.update_check import _upgrade_command
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.setattr("sys.prefix", "/home/user/venv")
        cmd = _upgrade_command()
        assert "pip install --upgrade" in cmd
        assert "git+https://github.com/Rouzax/CrateDigger" in cmd


class TestPrintCachedUpdateNotice:
    def _make_console(self):
        from io import StringIO

        from rich.console import Console
        buf = StringIO()
        return Console(file=buf, force_terminal=False, width=120), buf

    def test_newer_version_prints(self, tmp_path, mock_paths, monkeypatch):
        from festival_organizer.update_check import print_cached_update_notice
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setattr(
            "festival_organizer.update_check.importlib.metadata.version",
            lambda _: "0.6.7",
        )
        _write_cache(latest_version="0.7.0", ttl_seconds=86400)
        console, buf = self._make_console()
        print_cached_update_notice(console)
        out = buf.getvalue()
        assert "0.6.7" in out
        assert "0.7.0" in out
        assert "cratedigger" in out

    def test_same_version_silent(self, tmp_path, mock_paths, monkeypatch):
        from festival_organizer.update_check import print_cached_update_notice
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setattr(
            "festival_organizer.update_check.importlib.metadata.version",
            lambda _: "0.7.0",
        )
        _write_cache(latest_version="0.7.0", ttl_seconds=86400)
        console, buf = self._make_console()
        print_cached_update_notice(console)
        assert buf.getvalue() == ""

    def test_null_latest_silent(self, tmp_path, mock_paths, monkeypatch):
        from festival_organizer.update_check import print_cached_update_notice
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        _write_cache(latest_version=None, ttl_seconds=3600)
        console, buf = self._make_console()
        print_cached_update_notice(console)
        assert buf.getvalue() == ""

    def test_no_cache_silent(self, tmp_path, mock_paths, monkeypatch):
        from festival_organizer.update_check import print_cached_update_notice
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        console, buf = self._make_console()
        print_cached_update_notice(console)
        assert buf.getvalue() == ""

    def test_suppressed_silent(self, tmp_path, mock_paths, monkeypatch):
        from festival_organizer.update_check import print_cached_update_notice
        monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")
        _write_cache(latest_version="99.0.0", ttl_seconds=86400)
        console, buf = self._make_console()
        print_cached_update_notice(console)
        assert buf.getvalue() == ""


class TestRefreshUpdateCache:
    def test_stale_triggers_fetch_and_writes(self, tmp_path, mock_paths, monkeypatch):
        from unittest.mock import patch

        from festival_organizer.update_check import refresh_update_cache
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        old_entry = {
            "schema": SCHEMA_VERSION,
            "checked_at": 0,
            "ttl_seconds": 86400,
            "latest_version": "0.6.0",
        }
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(old_entry))

        with patch("festival_organizer.update_check._fetch_latest_release", return_value="0.7.0"):
            refresh_update_cache()

        entry = _read_cache()
        assert entry is not None
        assert entry["latest_version"] == "0.7.0"
        assert entry["ttl_seconds"] == 86400
        assert entry["checked_at"] > 0

    def test_fresh_skips_fetch(self, tmp_path, mock_paths, monkeypatch):
        from unittest.mock import patch

        from festival_organizer.update_check import refresh_update_cache
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        fresh_entry = {
            "schema": SCHEMA_VERSION,
            "checked_at": int(time.time()),
            "ttl_seconds": 86400,
            "latest_version": "0.7.0",
        }
        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(fresh_entry))

        with patch("festival_organizer.update_check._fetch_latest_release") as m:
            refresh_update_cache()
            m.assert_not_called()

    def test_missing_cache_triggers_fetch(self, tmp_path, mock_paths, monkeypatch):
        from unittest.mock import patch

        from festival_organizer.update_check import refresh_update_cache
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        with patch("festival_organizer.update_check._fetch_latest_release", return_value="0.7.0"):
            refresh_update_cache()

        entry = _read_cache()
        assert entry is not None
        assert entry["latest_version"] == "0.7.0"

    def test_fetch_failure_writes_short_ttl(self, tmp_path, mock_paths, monkeypatch):
        from unittest.mock import patch

        from festival_organizer.update_check import refresh_update_cache
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)

        with patch("festival_organizer.update_check._fetch_latest_release", return_value=None):
            refresh_update_cache()

        entry = _read_cache()
        assert entry is not None
        assert entry["latest_version"] is None
        assert entry["ttl_seconds"] == 3600

    def test_suppressed_no_op(self, tmp_path, mock_paths, monkeypatch):
        from unittest.mock import patch

        from festival_organizer.update_check import refresh_update_cache
        monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")

        with patch("festival_organizer.update_check._fetch_latest_release") as m:
            refresh_update_cache()
            m.assert_not_called()

        assert not _cache_path().exists()


class TestDebugLogging:
    """Tier 2: every silent-on-failure path in update_check leaves a DEBUG trail."""

    def test_fetch_latest_release_logs_debug_on_http_failure(self, caplog):
        import logging as _logging
        from urllib.error import URLError

        from festival_organizer.update_check import _fetch_latest_release
        with patch("festival_organizer.update_check.urlopen", side_effect=URLError("dns")):
            with caplog.at_level(_logging.DEBUG, logger="festival_organizer.update_check"):
                assert _fetch_latest_release() is None
        assert any("Update check HTTP failed" in r.message for r in caplog.records)
        assert any("dns" in r.message or "dns" in str(r.exc_info) for r in caplog.records)

    def test_is_suppressed_logs_env_var_reason(self, monkeypatch, caplog):
        import logging as _logging

        from festival_organizer.update_check import _is_suppressed
        monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")
        with caplog.at_level(_logging.DEBUG, logger="festival_organizer.update_check"):
            assert _is_suppressed()
        joined = "\n".join(r.message for r in caplog.records)
        assert "env var" in joined.lower()

    def test_is_suppressed_logs_non_tty_reason(self, monkeypatch, caplog):
        import logging as _logging

        from festival_organizer.update_check import _is_suppressed
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with caplog.at_level(_logging.DEBUG, logger="festival_organizer.update_check"):
            assert _is_suppressed()
        joined = "\n".join(r.message for r in caplog.records)
        assert "tty" in joined.lower()

    def test_is_suppressed_logs_isatty_exception_reason(self, monkeypatch, caplog):
        import logging as _logging

        from festival_organizer.update_check import _is_suppressed
        monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)

        def _raise():
            raise ValueError("io closed")
        monkeypatch.setattr("sys.stdout.isatty", _raise)
        with caplog.at_level(_logging.DEBUG, logger="festival_organizer.update_check"):
            assert _is_suppressed()
        joined = "\n".join(r.message for r in caplog.records)
        assert "isatty raised" in joined

    def test_read_cache_silent_on_missing_file(self, tmp_path, mock_paths, caplog):
        import logging as _logging

        with caplog.at_level(_logging.DEBUG, logger="festival_organizer.update_check"):
            assert _read_cache() is None
        assert not any("unreadable" in r.message for r in caplog.records)

    def test_read_cache_logs_debug_on_corrupt_json(self, tmp_path, mock_paths, caplog):
        import logging as _logging

        p = _cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not json {{{")
        with caplog.at_level(_logging.DEBUG, logger="festival_organizer.update_check"):
            assert _read_cache() is None
        assert any("unreadable" in r.message for r in caplog.records)
        assert any(str(p) in r.message for r in caplog.records)


def test_is_suppressed_explicit_true_when_env_var_set(monkeypatch):
    from festival_organizer import update_check

    monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")
    assert update_check._is_suppressed_explicit() is True


def test_is_suppressed_explicit_false_when_env_var_unset(monkeypatch):
    from festival_organizer import update_check

    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    assert update_check._is_suppressed_explicit() is False


def test_is_suppressed_explicit_ignores_tty(monkeypatch):
    """Explicit --version/--check paths must not suppress on non-TTY."""
    from festival_organizer import update_check

    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert update_check._is_suppressed_explicit() is False


def test_refresh_force_bypasses_freshness_check(monkeypatch, tmp_path):
    """force=True must fetch and write even when the cache is fresh."""
    import json
    import time

    from festival_organizer import update_check

    cache_file = tmp_path / "update-check.json"
    cache_file.write_text(json.dumps({
        "schema": update_check.SCHEMA_VERSION,
        "checked_at": int(time.time()),
        "ttl_seconds": 86400,
        "latest_version": "0.0.1",
    }), encoding="utf-8")

    monkeypatch.setattr(update_check, "_cache_path", lambda: cache_file)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)

    fetch_calls = []

    def fake_fetch():
        fetch_calls.append(1)
        return "9.9.9"

    monkeypatch.setattr(update_check, "_fetch_latest_release", fake_fetch)

    update_check.refresh_update_cache(force=True)

    assert fetch_calls == [1]
    written = json.loads(cache_file.read_text(encoding="utf-8"))
    assert written["latest_version"] == "9.9.9"


def test_refresh_default_respects_fresh_cache(monkeypatch, tmp_path):
    """force=False (default) preserves existing behaviour."""
    import json
    import time

    from festival_organizer import update_check

    cache_file = tmp_path / "update-check.json"
    cache_file.write_text(json.dumps({
        "schema": update_check.SCHEMA_VERSION,
        "checked_at": int(time.time()),
        "ttl_seconds": 86400,
        "latest_version": "0.0.1",
    }), encoding="utf-8")

    monkeypatch.setattr(update_check, "_cache_path", lambda: cache_file)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)

    fetch_calls = []
    monkeypatch.setattr(update_check, "_fetch_latest_release",
                        lambda: fetch_calls.append(1) or "9.9.9")

    update_check.refresh_update_cache()  # default force=False

    assert fetch_calls == []  # cache fresh, no fetch


def test_refresh_force_honours_explicit_suppression(monkeypatch, tmp_path):
    """With force=True, env-var suppression still applies; TTY does not."""
    from festival_organizer import update_check

    cache_file = tmp_path / "update-check.json"
    monkeypatch.setattr(update_check, "_cache_path", lambda: cache_file)

    fetch_calls = []
    monkeypatch.setattr(update_check, "_fetch_latest_release",
                        lambda: fetch_calls.append(1) or "9.9.9")

    monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")
    update_check.refresh_update_cache(force=True)
    assert fetch_calls == []
    assert not cache_file.exists()
