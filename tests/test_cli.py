import io
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from rich.console import Console

from festival_organizer.cli import run, _analyse_parallel, _run_kodi_sync, resolve_action
from festival_organizer.config import Config
from festival_organizer.operations import OperationResult
from tests.conftest import TEST_CONFIG


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
        if not isinstance(h, logging.handlers.RotatingFileHandler):
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
    assert resolve_action(
        source=tmp_path, output=tmp_path / "lib",
        move=False, dry_run=True,
    ) == "dry_run"
    assert resolve_action(
        source=tmp_path, output=tmp_path / "lib",
        move=True, dry_run=True,
    ) == "dry_run"


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

    with patch("festival_organizer.cli.analyse_file", side_effect=RuntimeError("mediainfo exploded")):
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

    with patch("festival_organizer.kodi.sync_library") as mock_sync, \
         patch("festival_organizer.kodi.KodiClient") as mock_client:
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
    results = [OperationResult(name="nfo", status="skipped", detail="exists", display_name="nfo")]
    pipeline_files, all_results = _make_kodi_inputs(tmp_path, [(video, results)])

    caplog.set_level(logging.DEBUG, logger="festival_organizer.kodi")
    with patch("festival_organizer.kodi.sync_library") as mock_sync, \
         patch("festival_organizer.kodi.KodiClient"):
        _run_kodi_sync(all_results, pipeline_files, cfg, Console(), quiet=True)

    mock_sync.assert_not_called()
    assert any(
        "no kodi-affecting changes" in rec.getMessage()
        for rec in caplog.records
        if rec.name == "festival_organizer.kodi"
    )


def test_check_flag_exists_and_exits_zero(monkeypatch):
    import festival_organizer.cli as cli_mod
    monkeypatch.setattr(cli_mod, "_run_check", lambda: 0)
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
    from festival_organizer import cli as cli_mod, metadata

    # Patch tool paths to non-None values
    for attr in ("FFPROBE_PATH", "MEDIAINFO_PATH", "MKVEXTRACT_PATH", "MKVPROPEDIT_PATH", "MKVMERGE_PATH"):
        monkeypatch.setattr(metadata, attr, "/usr/bin/fake")

    # Patch subprocess to return a fake version line
    import subprocess
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: type("R", (), {"stdout": "fake 1.0\n", "stderr": "", "returncode": 0})(),
    )

    # cv2 present
    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", True)

    # Create real files under tmp_path so is_file() works correctly.
    # Asset probe is routed through the paths module, so patch the
    # data_dir / cookies_file helpers rather than faking Path.home().
    data_dir = tmp_path / "CrateDigger"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text("")
    (data_dir / "festivals.json").write_text("{}")
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
        "festival_organizer.cli.paths.festivals_file",
        lambda: data_dir / "festivals.json",
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
    fake_config = type("C", (), {
        "tracklists_credentials": ("a@b.com", "pass"),
        "fanart_personal_api_key": "key",
        "kodi_enabled": False,
        "kodi_host": "",
    })()
    monkeypatch.setattr("festival_organizer.config.load_config", lambda: fake_config)

    # importlib.metadata.version always succeeds
    monkeypatch.setattr("importlib.metadata.version", lambda pkg: "9.9.9")

    con, buf = _make_test_console()
    code = cli_mod._run_check_impl(con)  # type: ignore[reportAttributeAccessIssue]
    assert code == 0
    output = buf.getvalue()
    assert "All checks passed" in output


def test_run_check_impl_required_tool_missing_exits_one(monkeypatch, tmp_path):
    from festival_organizer import cli as cli_mod, metadata

    # All tool paths None (missing)
    for attr in ("FFPROBE_PATH", "MEDIAINFO_PATH", "MKVEXTRACT_PATH", "MKVPROPEDIT_PATH", "MKVMERGE_PATH"):
        monkeypatch.setattr(metadata, attr, None)

    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", False)
    # Point every asset probe at a path under tmp_path that does not exist,
    # so all is_file() checks return False.
    missing = tmp_path / "missing"
    for name in ("config_file", "festivals_file", "artists_file", "artist_mbids_file", "cookies_file"):
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
    from festival_organizer import cli as cli_mod, metadata

    for attr in ("FFPROBE_PATH", "MEDIAINFO_PATH", "MKVEXTRACT_PATH", "MKVPROPEDIT_PATH", "MKVMERGE_PATH"):
        monkeypatch.setattr(metadata, attr, "/usr/bin/fake")

    import subprocess
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: type("R", (), {"stdout": "fake 1.0\n", "stderr": "", "returncode": 0})(),
    )
    monkeypatch.setattr("festival_organizer.frame_sampler._HAS_CV2", True)

    # Create real files under tmp_path so is_file() works correctly.
    # Route every probe through the paths module so the test is insulated
    # from platform-specific defaults.
    data_dir = tmp_path / "CrateDigger"
    data_dir.mkdir()
    (data_dir / "config.toml").write_text("")
    (data_dir / "festivals.json").write_text("{}")
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
        "festival_organizer.cli.paths.festivals_file",
        lambda: data_dir / "festivals.json",
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

    fake_config = type("C", (), {
        "tracklists_credentials": ("a@b.com", "pass"),
        "fanart_personal_api_key": "key",
        "kodi_enabled": False,
        "kodi_host": "",
    })()
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

    results = [OperationResult(name="posters", status="done", display_name="album_poster")]
    pipeline_files, all_results = _make_kodi_inputs(tmp_path, [(video_a, results)])

    with patch("festival_organizer.kodi.sync_library") as mock_sync, \
         patch("festival_organizer.kodi.KodiClient"):
        _run_kodi_sync(all_results, pipeline_files, cfg, Console(), quiet=True)

    mock_sync.assert_called_once()
    called_paths = mock_sync.call_args[0][1]
    assert video_a in called_paths
    assert video_b in called_paths
    assert not any(p.suffix == ".txt" for p in called_paths)


def test_config_option_help_mentions_toml():
    """The --config flag's help string must reference config.toml, not config.json."""
    from festival_organizer.cli import app
    from typer.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(app, ["organize", "--help"])
    assert result.exit_code == 0
    assert "config.toml" in result.stdout
    assert "config.json" not in result.stdout
