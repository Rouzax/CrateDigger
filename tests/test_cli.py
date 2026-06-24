import io
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from festival_organizer.cli import (
    _analyse_parallel,
    _run_kodi_sync,
    resolve_action,
    run,
)
from festival_organizer.config import Config
from festival_organizer.operations import OperationResult
from tests.conftest import TEST_CONFIG


def test_layout_enum_only_exposes_place_named_layouts():
    """The --layout flag exposes only the canonical place_* names.

    Festival-named layouts were removed in 0.15.0; users with
    `default_layout = "festival_flat"` in config.toml are migrated by
    `_migrate_layout_names` at load time, but the CLI flag only accepts
    the canonical names.
    """
    from festival_organizer.cli import Layout

    values = {layout.value for layout in Layout}
    assert values == {"artist_flat", "place_flat", "artist_nested", "place_nested"}


def test_version_flag_prints_version_and_exits():
    """--version should print the installed version and exit 0."""
    from typer.testing import CliRunner

    from festival_organizer.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    from importlib.metadata import version

    assert version("cratedigger") in result.stdout


def test_run_no_command():
    """No command prints help and returns 1."""
    assert run([]) == 1


def test_run_nonexistent_path():
    """Nonexistent path returns 1 with error message."""
    assert run(["organize", "--dry-run", "/nonexistent/path/abc123"]) == 1


def test_run_unexpected_error_returns_1(capsys):
    """Unexpected exception is caught, printed to stderr, returns 1."""
    with patch("festival_organizer.cli.load_config", side_effect=RuntimeError("boom")):
        result = run(["organize", "--dry-run", "/tmp"])
    assert result == 1
    captured = capsys.readouterr()
    assert "boom" in captured.err


def _console_handler_level():
    """Return the level of the non-file handler (the user-visible console handler)."""
    import logging.handlers

    logger = logging.getLogger("festival_organizer")
    for h in logger.handlers:
        if not isinstance(h, (logging.handlers.MemoryHandler, logging.FileHandler)):
            return h.level
    raise AssertionError("no console handler found")


def test_verbose_flag_enables_info_logging():
    """The --verbose flag sets the console handler to INFO."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.resolve_library_root", return_value=None):
            run(["organize", "--dry-run", "/tmp", "--verbose"])
    assert _console_handler_level() == logging.INFO


def test_debug_flag_enables_debug_logging():
    """The --debug flag sets the console handler to DEBUG."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.resolve_library_root", return_value=None):
            run(["organize", "--dry-run", "/tmp", "--debug"])
    assert _console_handler_level() == logging.DEBUG


def test_organize_dry_run_move_conflict(capsys):
    """--dry-run and --move cannot be used together."""
    result = run(["organize", "/tmp", "--dry-run", "--move"])
    assert result != 0


def test_organize_rename_only_flag_is_gone(capsys):
    """--rename-only was removed: smart default now picks rename for in-place
    runs automatically, so the flag became redundant and was dropped."""
    result = run(["organize", "/tmp", "--rename-only"])
    assert result != 0  # Typer rejects unknown flag


# ── resolve_action tests ──────────────────────────────────────────────


def test_resolve_action_dry_run_wins(tmp_path):
    """--dry-run overrides everything; action is 'dry_run'."""
    assert (
        resolve_action(
            source=tmp_path,
            output=tmp_path / "lib",
            move=False,
            dry_run=True,
        )
        == "dry_run"
    )
    assert (
        resolve_action(
            source=tmp_path,
            output=tmp_path / "lib",
            move=True,
            dry_run=True,
        )
        == "dry_run"
    )


def test_resolve_action_in_place_is_rename(tmp_path):
    """When source equals output, the default action is rename (atomic,
    same-filesystem guaranteed). --move has no effect in this case."""
    lib = tmp_path / "lib"
    lib.mkdir()
    assert resolve_action(source=lib, output=lib, move=False, dry_run=False) == "rename"
    assert resolve_action(source=lib, output=lib, move=True, dry_run=False) == "rename"


def test_resolve_action_source_inside_output_is_rename(tmp_path):
    """When source is a descendant of output (e.g. organizing a subfolder of
    an existing library), the default is still rename — we're reorganizing
    within the library, not importing across it."""
    lib = tmp_path / "lib"
    sub = lib / "Artist"
    sub.mkdir(parents=True)
    assert resolve_action(source=sub, output=lib, move=False, dry_run=False) == "rename"


def test_resolve_action_import_default_is_copy(tmp_path):
    """Disjoint source/output defaults to copy: the user is importing, and the
    safe default is to leave the source untouched."""
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    inbox.mkdir()
    lib.mkdir()
    assert resolve_action(source=inbox, output=lib, move=False, dry_run=False) == "copy"


def test_resolve_action_import_with_move(tmp_path):
    """Disjoint source/output with --move: clear the inbox after copying."""
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    inbox.mkdir()
    lib.mkdir()
    assert resolve_action(source=inbox, output=lib, move=True, dry_run=False) == "move"


def test_organize_inside_library_requires_confirmation(tmp_path, capsys):
    """Organize inside existing library without --yes aborts in non-interactive."""
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)

    with patch("festival_organizer.cli.resolve_library_root", return_value=lib):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = run(["organize", str(lib)])

    assert result == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "confirmation" in combined.lower() or "--yes" in combined


def test_organize_inside_library_with_yes_proceeds(tmp_path):
    """Organize inside library with --yes skips confirmation."""
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)

    with patch("festival_organizer.cli.resolve_library_root", return_value=lib):
        with patch("festival_organizer.cli.scan_folder", return_value=[]):
            result = run(["organize", str(lib), "--yes"])

    assert result == 0


def test_organize_with_explicit_output_no_confirmation(tmp_path):
    """Organize with explicit -o never prompts for confirmation."""
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()

    with patch("festival_organizer.cli.resolve_library_root", return_value=lib):
        with patch("festival_organizer.cli.scan_folder", return_value=[]):
            result = run(["organize", str(lib), "-o", str(out)])

    assert result == 0


# ---------------------------------------------------------------------------
# _analyse_parallel tests
# ---------------------------------------------------------------------------


def test_analyse_parallel_preserves_order():
    """Parallel analysis must return results in the same order as input files."""
    cfg = Config(TEST_CONFIG)
    files = [Path(f"/fake/file{i}.mkv") for i in range(10)]
    root = Path("/fake")

    def fake_analyse(fp, r, c):
        mf = MagicMock()
        mf.artist = fp.stem
        return mf

    def fake_classify(mf, r, c):
        return "festival_set"

    with patch("festival_organizer.cli.analyse_file", side_effect=fake_analyse):
        with patch("festival_organizer.cli.classify", side_effect=fake_classify):
            result = _analyse_parallel(files, root, cfg, max_workers=4)

    assert len(result) == 10
    for i, (fp, mf) in enumerate(result):
        assert fp == files[i], f"File at index {i} out of order"
        assert mf.artist == f"file{i}"
        assert mf.content_type == "festival_set"


def test_analyse_parallel_single_file():
    """Single file should work without issues."""
    cfg = Config(TEST_CONFIG)
    files = [Path("/fake/solo.mkv")]
    root = Path("/fake")

    def fake_analyse(fp, r, c):
        mf = MagicMock()
        mf.artist = "solo"
        return mf

    def fake_classify(mf, r, c):
        return "unknown"

    with patch("festival_organizer.cli.analyse_file", side_effect=fake_analyse):
        with patch("festival_organizer.cli.classify", side_effect=fake_classify):
            result = _analyse_parallel(files, root, cfg, max_workers=4)

    assert len(result) == 1
    assert result[0][1].content_type == "unknown"


def test_analyse_parallel_empty_list():
    """Empty file list should return empty list without errors."""
    cfg = Config(TEST_CONFIG)
    result = _analyse_parallel([], Path("/fake"), cfg)
    assert result == []


def test_enrich_uses_parallel_analysis(tmp_path):
    """Enrich command should use _analyse_parallel for the analysis phase."""
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)
    fake_file = lib / "test.mkv"
    fake_file.touch()

    with patch("festival_organizer.cli.resolve_library_root", return_value=lib):
        with patch("festival_organizer.cli.scan_folder", return_value=[fake_file]):
            with patch("festival_organizer.cli._analyse_parallel") as mock_parallel:
                mock_mf = MagicMock()
                mock_mf.content_type = "festival_set"
                mock_mf.festival = "TestFest"
                mock_mf.artist = "TestArtist"
                mock_mf.source_path = fake_file
                mock_parallel.return_value = [(fake_file, mock_mf)]
                with patch("festival_organizer.cli.run_pipeline", return_value=[]):
                    run(["enrich", str(lib), "--verbose"])

    mock_parallel.assert_called_once()
    call_args = mock_parallel.call_args
    assert call_args[0][0] == [fake_file]  # files
    assert call_args[0][1] == lib  # root


def test_analyse_parallel_propagates_exception():
    """If analyse_file raises, the exception should propagate."""
    cfg = Config(TEST_CONFIG)
    files = [Path("/fake/bad.mkv")]
    root = Path("/fake")

    with patch(
        "festival_organizer.cli.analyse_file",
        side_effect=RuntimeError("mediainfo exploded"),
    ):
        with pytest.raises(RuntimeError, match="mediainfo exploded"):
            _analyse_parallel(files, root, cfg, max_workers=4)


class _StubOp:
    def __init__(self, name: str):
        self.name = name


def _make_kodi_inputs(tmp_path, results_per_file):
    """Build (pipeline_files, all_results) for a list of (video_path, [OperationResult])."""
    pipeline_files = []
    all_results = []
    for video, results in results_per_file:
        ops = [_StubOp(r.name) for r in results]
        pipeline_files.append((video, MagicMock(), ops))
        all_results.append(results)
    return pipeline_files, all_results


def test_run_kodi_sync_calls_sync_library_when_op_done(tmp_path):
    """A 'done' nfo result should trigger sync_library with the video path."""
    cfg = Config(TEST_CONFIG)
    video = tmp_path / "set.mkv"
    video.touch()
    results = [OperationResult(name="nfo", status="done", display_name="nfo")]
    pipeline_files, all_results = _make_kodi_inputs(tmp_path, [(video, results)])

    with (
        patch("festival_organizer.kodi.sync_library") as mock_sync,
        patch("festival_organizer.kodi.KodiClient") as mock_client,
    ):
        _run_kodi_sync(all_results, pipeline_files, cfg, Console(), quiet=True)

    mock_client.assert_called_once()
    mock_sync.assert_called_once()
    called_paths = mock_sync.call_args[0][1]
    assert video in called_paths


def test_run_kodi_sync_empty_logs_debug_and_skips_sync(tmp_path, caplog):
    """All-skipped pipeline should log DEBUG and not invoke sync_library."""
    cfg = Config(TEST_CONFIG)
    video = tmp_path / "set.mkv"
    video.touch()
    results = [
        OperationResult(
            name="nfo", status="skipped", detail="exists", display_name="nfo"
        )
    ]
    pipeline_files, all_results = _make_kodi_inputs(tmp_path, [(video, results)])

    caplog.set_level(logging.DEBUG, logger="festival_organizer.kodi")
    with (
        patch("festival_organizer.kodi.sync_library") as mock_sync,
        patch("festival_organizer.kodi.KodiClient"),
    ):
        _run_kodi_sync(all_results, pipeline_files, cfg, Console(), quiet=True)

    mock_sync.assert_not_called()
    assert any(
        "kodi.sync: status=skipped" in rec.getMessage()
        for rec in caplog.records
        if rec.name == "festival_organizer.kodi"
    )


def test_check_flag_exists_and_exits_zero(monkeypatch, tmp_path):
    import festival_organizer.cli as cli_mod
    from festival_organizer import paths

    monkeypatch.setattr(cli_mod, "_run_check_impl", lambda con: 0)
    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(cli_mod.app, ["--check"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# _run_check_impl tests
# ---------------------------------------------------------------------------


def _make_test_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    con = Console(file=buf, highlight=False, markup=True)
    return con, buf


def test_run_check_impl_all_pass(monkeypatch, tmp_path):
    from festival_organizer import cli as cli_mod
    from festival_organizer import metadata

    # Patch tool paths to non-None values
    for attr in (
        "FFPROBE_PATH",
        "MKVEXTRACT_PATH",
        "MKVPROPEDIT_PATH",
        "MKVMERGE_PATH",
    ):
        monkeypatch.setattr(metadata, attr, "/usr/bin/fake")

    # Patch subprocess to return a fake version line
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type(
            "R", (), {"stdout": "fake 1.0\n", "stderr": "", "returncode": 0}
        )(),
    )

    # cv2 present
    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", True)

    # Create real files under tmp_path so is_file() works correctly.
    # Asset probe is routed through the paths module, so patch the
    # data_dir / cookies_file helpers rather than faking Path.home().
    data_dir = tmp_path / "CrateDigger"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text("")
    (data_dir / "places.json").write_text("{}")
    (data_dir / "artists.json").write_text("{}")
    (data_dir / "artist_mbids.json").write_text("{}")
    cookie_path = tmp_path / "state" / "1001tl-cookies.json"
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text("[]")
    monkeypatch.setattr(
        "festival_organizer.cli.paths.config_file",
        lambda: data_dir / "config.toml",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.places_file",
        lambda: data_dir / "places.json",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.artists_file",
        lambda: data_dir / "artists.json",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.artist_mbids_file",
        lambda: data_dir / "artist_mbids.json",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.cookies_file", lambda: cookie_path
    )

    # load_config returns a config with credentials set
    fake_config = type(
        "C",
        (),
        {
            "tracklists_credentials": ("a@b.com", "pass"),
            "fanart_personal_api_key": "key",
            "kodi_enabled": False,
            "kodi_host": "",
        },
    )()
    monkeypatch.setattr("festival_organizer.config.load_config", lambda: fake_config)

    # importlib.metadata.version always succeeds
    monkeypatch.setattr("importlib.metadata.version", lambda pkg: "9.9.9")

    con, buf = _make_test_console()
    code = cli_mod._run_check_impl(con)  # type: ignore[reportAttributeAccessIssue]
    assert code == 0
    output = buf.getvalue()
    assert "All checks passed" in output


def test_run_check_impl_required_tool_missing_exits_one(monkeypatch, tmp_path):
    from festival_organizer import cli as cli_mod
    from festival_organizer import metadata

    # All tool paths None (missing)
    for attr in (
        "FFPROBE_PATH",
        "MKVEXTRACT_PATH",
        "MKVPROPEDIT_PATH",
        "MKVMERGE_PATH",
    ):
        monkeypatch.setattr(metadata, attr, None)

    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", False)
    # Point every asset probe at a path under tmp_path that does not exist,
    # so all is_file() checks return False.
    missing = tmp_path / "missing"
    for name in (
        "config_file",
        "places_file",
        "artists_file",
        "artist_mbids_file",
        "cookies_file",
    ):
        monkeypatch.setattr(
            f"festival_organizer.cli.paths.{name}",
            lambda _n=name: missing / _n,
        )

    def _raise():
        raise RuntimeError("no config")

    monkeypatch.setattr("festival_organizer.config.load_config", _raise)
    monkeypatch.setattr("importlib.metadata.version", lambda pkg: "9.9.9")

    con, buf = _make_test_console()
    code = cli_mod._run_check_impl(con)  # type: ignore[reportAttributeAccessIssue]
    assert code == 1
    assert "error" in buf.getvalue().lower()


def test_run_check_impl_shows_all_section_headers(monkeypatch, tmp_path):
    from festival_organizer import cli as cli_mod
    from festival_organizer import metadata

    for attr in (
        "FFPROBE_PATH",
        "MKVEXTRACT_PATH",
        "MKVPROPEDIT_PATH",
        "MKVMERGE_PATH",
    ):
        monkeypatch.setattr(metadata, attr, "/usr/bin/fake")

    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: type(
            "R", (), {"stdout": "fake 1.0\n", "stderr": "", "returncode": 0}
        )(),
    )
    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", True)

    # Create real files under tmp_path so is_file() works correctly.
    # Route every probe through the paths module so the test is insulated
    # from platform-specific defaults.
    data_dir = tmp_path / "CrateDigger"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text("")
    (data_dir / "places.json").write_text("{}")
    (data_dir / "artists.json").write_text("{}")
    (data_dir / "artist_mbids.json").write_text("{}")
    cookie_path = tmp_path / "state" / "1001tl-cookies.json"
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text("[]")
    monkeypatch.setattr(
        "festival_organizer.cli.paths.config_file",
        lambda: data_dir / "config.toml",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.places_file",
        lambda: data_dir / "places.json",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.artists_file",
        lambda: data_dir / "artists.json",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.artist_mbids_file",
        lambda: data_dir / "artist_mbids.json",
    )
    monkeypatch.setattr(
        "festival_organizer.cli.paths.cookies_file", lambda: cookie_path
    )

    fake_config = type(
        "C",
        (),
        {
            "tracklists_credentials": ("a@b.com", "pass"),
            "fanart_personal_api_key": "key",
            "kodi_enabled": False,
            "kodi_host": "",
        },
    )()
    monkeypatch.setattr("festival_organizer.config.load_config", lambda: fake_config)
    monkeypatch.setattr("importlib.metadata.version", lambda pkg: "9.9.9")

    con, buf = _make_test_console()
    cli_mod._run_check_impl(con)  # type: ignore[reportAttributeAccessIssue]
    output = buf.getvalue()
    assert "Tools" in output
    assert "Config" in output
    assert "Credentials" in output
    assert "Python packages" in output


def test_run_kodi_sync_album_poster_expands_to_folder_siblings(tmp_path):
    """album_poster display_name should fan out to every video sibling in the folder."""
    cfg = Config(TEST_CONFIG)
    folder = tmp_path / "festival"
    folder.mkdir()
    video_a = folder / "a.mkv"
    video_b = folder / "b.mkv"
    video_a.touch()
    video_b.touch()
    # Also add a non-video file to confirm filtering
    (folder / "notes.txt").write_text("x")

    results = [
        OperationResult(name="posters", status="done", display_name="album_poster")
    ]
    pipeline_files, all_results = _make_kodi_inputs(tmp_path, [(video_a, results)])

    with (
        patch("festival_organizer.kodi.sync_library") as mock_sync,
        patch("festival_organizer.kodi.KodiClient"),
    ):
        _run_kodi_sync(all_results, pipeline_files, cfg, Console(), quiet=True)

    mock_sync.assert_called_once()
    called_paths = mock_sync.call_args[0][1]
    assert video_a in called_paths
    assert video_b in called_paths
    assert not any(p.suffix == ".txt" for p in called_paths)


def test_config_option_help_mentions_toml():
    """The --config flag's help string must reference config.toml, not config.json."""
    from typer.testing import CliRunner

    from festival_organizer.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["organize", "--help"])
    assert result.exit_code == 0
    assert "config.toml" in result.stdout
    assert "config.json" not in result.stdout


def test_version_prints_version_then_latest(monkeypatch, tmp_path):
    """When installed == latest, output ends with '(latest)'."""
    from importlib.metadata import version

    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    installed = version("cratedigger")
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: installed)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert f"cratedigger {installed}" in result.stdout
    assert "(latest)" in result.stdout


def test_version_prints_stale_notice(monkeypatch, tmp_path):
    """When a newer release exists, the stale 2-line notice prints."""
    from importlib.metadata import version

    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    installed = version("cratedigger")
    parts = installed.split(".")
    bumped = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: bumped)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert f"cratedigger {installed}" in result.stdout
    assert "newer version is available" in result.stdout or f"{bumped}" in result.stdout


def test_version_silent_on_fetch_failure(monkeypatch, tmp_path):
    """Fetch returning None yields just the version line, no exception."""
    from importlib.metadata import version

    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    installed = version("cratedigger")
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: None)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert f"cratedigger {installed}" in result.stdout
    assert "newer version" not in result.stdout
    assert "(latest)" not in result.stdout


def test_version_honours_env_var_suppression(monkeypatch, tmp_path):
    """CRATEDIGGER_NO_UPDATE_CHECK=1 skips the network call entirely."""
    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    fetch_calls = []
    monkeypatch.setattr(
        update_check, "_fetch_latest_release", lambda: fetch_calls.append(1) or "9.9.9"
    )
    monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert fetch_calls == []
    assert "newer version" not in result.stdout
    assert "(latest)" not in result.stdout


def test_check_attaches_file_handler(monkeypatch, tmp_path):
    """--check must populate the per-command log with at least one DEBUG record."""
    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: None)

    runner = CliRunner()
    runner.invoke(cli.app, ["--check"])

    # Flush buffered records (MemoryHandler defers writes until close/flush).
    # In real usage, logging.shutdown() handles this at interpreter exit.
    for h in logging.getLogger("festival_organizer").handlers:
        h.close()

    log_files = list(tmp_path.glob("*.log"))
    assert log_files, "log file should have been created by --check"
    content = log_files[0].read_text(encoding="utf-8")
    assert "festival_organizer" in content, (
        "expected at least one festival_organizer record in log"
    )


def test_version_attaches_file_handler(monkeypatch, tmp_path):
    """--version must also populate the per-command log."""
    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: None)

    runner = CliRunner()
    runner.invoke(cli.app, ["--version"])

    # Flush buffered records (MemoryHandler defers writes until close/flush).
    for h in logging.getLogger("festival_organizer").handlers:
        h.close()

    log_files = list(tmp_path.glob("*.log"))
    assert log_files, "log file should have been created by --version"
    content = log_files[0].read_text(encoding="utf-8")
    assert "festival_organizer.update_check" in content, (
        "expected at least one update_check DEBUG record in log"
    )


def test_check_update_status_row_current(monkeypatch, tmp_path):
    """Update status: current installed version returns (latest)."""
    from importlib.metadata import version

    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    installed = version("cratedigger")
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: installed)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--check"])
    assert "Update status" in result.stdout
    assert "(latest)" in result.stdout


def test_check_update_status_row_stale(monkeypatch, tmp_path):
    """Update status: newer release available counts as a warning."""
    from importlib.metadata import version

    from typer.testing import CliRunner

    from festival_organizer import cli, paths, update_check

    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)
    installed = version("cratedigger")
    parts = installed.split(".")
    bumped = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: bumped)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--check"])
    assert "Update status" in result.stdout
    assert f"newer: {bumped}" in result.stdout
    # Stale should be reported as a warning in the summary
    assert "warning" in result.stdout.lower()


def test_check_update_status_row_suppressed(monkeypatch, tmp_path):
    """Update status: env var suppression shows informational ~ line."""
    from typer.testing import CliRunner

    from festival_organizer import cli, paths

    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    monkeypatch.setenv("CRATEDIGGER_NO_UPDATE_CHECK", "1")

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--check"])
    assert "Update status" in result.stdout
    assert "suppressed" in result.stdout


# ---------------------------------------------------------------------------
# _youtube_lookup + worker YouTube-anchored search tests
# ---------------------------------------------------------------------------


def test_youtube_lookup_queries_watch_url():
    """A file with an embedded YouTube id queries the watch-URL and returns hits."""
    from festival_organizer.tracklists.cli_handler import _youtube_lookup

    captured = []

    class S:
        def search(self, q, **kw):
            captured.append(q)
            return ["RESULT"] if q.startswith("https://www.youtube.com/watch") else []

    res = _youtube_lookup(S(), Path("Set [p-nL0FjuCPs].mkv"), "p-nL0FjuCPs")
    assert res == ["RESULT"]
    assert captured == ["https://www.youtube.com/watch?v=p-nL0FjuCPs"]


def test_youtube_lookup_no_id_returns_empty():
    """No embedded id: the watch-URL search must not run, return []."""
    from festival_organizer.tracklists.cli_handler import _youtube_lookup

    class S:
        def search(self, q, **kw):
            raise AssertionError("should not search without an id")

    assert _youtube_lookup(S(), Path("Set.mkv"), "") == []


def _make_identify_mf(youtube_id: str = "", duration_seconds: float = 3600.0):
    """Minimal MediaFile-like stand-in for the identify worker."""
    mf = MagicMock()
    mf.youtube_id = youtube_id
    mf.duration_seconds = duration_seconds
    mf.year = None
    mf.content_type = "festival_set"
    return mf


def _search_result(rid: str, url: str, date: str | None = None):
    from festival_organizer.tracklists.scoring import SearchResult

    return SearchResult(id=rid, title=f"Title {rid}", url=url, date=date)


def _run_worker_for_youtube(tmp_path, monkeypatch, *, search_side_effect, auto_select):
    """Drive _process_file for a no-stored-tags file with a mocked session.search.

    Returns (status_tuple, fetch_calls, search_queries).
    """
    from festival_organizer.tracklists import cli_handler

    fake = tmp_path / "Set [p-nL0FjuCPs].mkv"
    fake.write_bytes(b"")

    search_queries: list[str] = []

    def _search(q, **kw):
        search_queries.append(q)
        return search_side_effect(q)

    session = MagicMock()
    session.search.side_effect = _search

    fetch_calls: list[dict] = []

    def _fake_fetch(*args, **kwargs):
        fetch_calls.append(kwargs)
        return ("updated", "updated", "ok")

    mf = _make_identify_mf(youtube_id="p-nL0FjuCPs")

    monkeypatch.setattr(cli_handler, "analyse_file", lambda *a, **k: mf)
    monkeypatch.setattr(cli_handler, "classify", lambda *a, **k: "festival_set")
    monkeypatch.setattr(
        cli_handler, "extract_stored_tracklist_info", lambda *a, **k: None
    )
    monkeypatch.setattr(
        cli_handler, "build_search_query", lambda fp: "fuzzy text query"
    )
    monkeypatch.setattr(cli_handler, "_fetch_and_embed", _fake_fetch)
    # Auto-select-only path: _select_interactive should be chosen by selecting
    # the top scored result; stub it to return its first argument's first entry.
    monkeypatch.setattr(
        cli_handler,
        "_select_interactive",
        lambda scored, *a, **k: scored[0] if scored else None,
    )

    status = cli_handler._process_file(
        filepath=fake,
        scan_root=tmp_path,
        session=session,
        config=Config(TEST_CONFIG),
        search_expansion={},
        tracklist_input=None,
        auto_select=auto_select,
        ignore_stored=False,
        preview=False,
        quiet=True,
        language="eng",
        console=Console(file=io.StringIO()),
    )
    return status, fetch_calls, search_queries


def test_worker_single_youtube_hit_bypasses_picker_auto(tmp_path, monkeypatch):
    """One watch-URL hit feeds straight into _fetch_and_embed; no text search."""

    def side_effect(q):
        if q.startswith("https://www.youtube.com/watch"):
            return [
                _search_result("2wtsw119", "https://1001.tl/2wtsw119", "2024-01-01")
            ]
        raise AssertionError(f"unexpected text search: {q}")

    status, fetch_calls, queries = _run_worker_for_youtube(
        tmp_path, monkeypatch, search_side_effect=side_effect, auto_select=True
    )

    assert status[0] == "updated"
    assert queries == ["https://www.youtube.com/watch?v=p-nL0FjuCPs"]
    assert len(fetch_calls) == 1
    assert fetch_calls[0]["youtube_id"] == "p-nL0FjuCPs"
    assert fetch_calls[0]["tracklist_id"] == "2wtsw119"


def test_worker_single_youtube_hit_bypasses_picker_interactive(tmp_path, monkeypatch):
    """Single hit also bypasses the picker in interactive mode."""

    def side_effect(q):
        if q.startswith("https://www.youtube.com/watch"):
            return [_search_result("2wtsw119", "https://1001.tl/2wtsw119")]
        raise AssertionError(f"unexpected text search: {q}")

    status, fetch_calls, queries = _run_worker_for_youtube(
        tmp_path, monkeypatch, search_side_effect=side_effect, auto_select=False
    )

    assert status[0] == "updated"
    assert queries == ["https://www.youtube.com/watch?v=p-nL0FjuCPs"]
    assert len(fetch_calls) == 1
    assert fetch_calls[0]["youtube_id"] == "p-nL0FjuCPs"


def test_worker_multi_youtube_hits_score_among_candidates(tmp_path, monkeypatch):
    """Several hits go through scoring/selection over only the anchored set."""
    anchored = [
        _search_result("aaa", "https://1001.tl/aaa"),
        _search_result("bbb", "https://1001.tl/bbb"),
    ]

    def side_effect(q):
        if q.startswith("https://www.youtube.com/watch"):
            return anchored
        raise AssertionError(f"text search must not run: {q}")

    captured = {}

    def fake_score(results, query_parts, duration_mins):
        captured["results"] = results
        return results

    from festival_organizer.tracklists import cli_handler

    monkeypatch.setattr(cli_handler, "score_results", fake_score)

    status, fetch_calls, queries = _run_worker_for_youtube(
        tmp_path, monkeypatch, search_side_effect=side_effect, auto_select=False
    )

    # Only the watch-URL query ran; the broad fuzzy text query never did.
    assert queries == ["https://www.youtube.com/watch?v=p-nL0FjuCPs"]
    # Scoring was given exactly the anchored candidate set.
    assert captured["results"] == anchored
    assert len(fetch_calls) == 1
    assert fetch_calls[0]["youtube_id"] == "p-nL0FjuCPs"


def test_worker_zero_youtube_hits_falls_back_to_text_search(tmp_path, monkeypatch):
    """No watch-URL hits: fall back to today's fuzzy text search exactly."""
    text_hit = [_search_result("ccc", "https://1001.tl/ccc")]

    def side_effect(q):
        if q.startswith("https://www.youtube.com/watch"):
            return []
        return text_hit

    from festival_organizer.tracklists import cli_handler

    monkeypatch.setattr(
        cli_handler, "score_results", lambda results, parts, dur: results
    )

    status, fetch_calls, queries = _run_worker_for_youtube(
        tmp_path, monkeypatch, search_side_effect=side_effect, auto_select=False
    )

    # Both the watch-URL probe AND the fuzzy text search ran, in order.
    assert queries[0] == "https://www.youtube.com/watch?v=p-nL0FjuCPs"
    assert "fuzzy text query" in queries[1]
    assert len(fetch_calls) == 1
    assert fetch_calls[0]["youtube_id"] == "p-nL0FjuCPs"


def test_check_clean_install_reports_all_passed(monkeypatch, tmp_path):
    """A clean install with required tools, optional cv2 absent, no
    artists.json/artist_mbids.json, and 1001TL credentials configured should
    report 'All checks passed.', not warning about optional items."""
    from importlib.metadata import version

    from typer.testing import CliRunner

    from festival_organizer import cli, metadata, paths, update_check

    # Required tools all present
    for attr in (
        "FFPROBE_PATH",
        "MKVEXTRACT_PATH",
        "MKVPROPEDIT_PATH",
        "MKVMERGE_PATH",
    ):
        monkeypatch.setattr(metadata, attr, "/usr/bin/true")
    # cv2/numpy absent
    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", False)

    # Required config files present, optional ones absent.
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[tracklists]\nemail = 'test@example.com'\npassword = 'secret'\n",
        encoding="utf-8",
    )
    places_path = tmp_path / "places.json"
    places_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "config_file", lambda: config_path)
    monkeypatch.setattr(paths, "places_file", lambda: places_path)
    # Optional assets absent
    monkeypatch.setattr(
        paths, "artists_file", lambda: tmp_path / "missing-artists.json"
    )
    monkeypatch.setattr(
        paths, "artist_mbids_file", lambda: tmp_path / "missing-mbids.json"
    )
    monkeypatch.setattr(paths, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "cookies_file", lambda: tmp_path / "missing-cookies.txt")

    # Update status: current
    installed = version("cratedigger")
    monkeypatch.setattr(update_check, "_fetch_latest_release", lambda: installed)
    monkeypatch.delenv("CRATEDIGGER_NO_UPDATE_CHECK", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["--check"])
    out = result.stdout

    # The summary should show "All checks passed.", not any warnings.
    assert "All checks passed" in out, (
        f"expected 'All checks passed' in output, got:\n{out}"
    )
