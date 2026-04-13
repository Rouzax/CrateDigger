import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from rich.console import Console

from festival_organizer.cli import run, _analyse_parallel, _run_kodi_sync
from festival_organizer.config import Config
from festival_organizer.operations import OperationResult
from tests.conftest import TEST_CONFIG


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


def test_verbose_flag_enables_info_logging():
    """The --verbose flag enables INFO logging for the package."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.resolve_library_root", return_value=None):
            run(["organize", "--dry-run", "/tmp", "--verbose"])
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.INFO


def test_debug_flag_enables_debug_logging():
    """The --debug flag enables DEBUG logging for the package."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.resolve_library_root", return_value=None):
            run(["organize", "--dry-run", "/tmp", "--debug"])
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.DEBUG


def test_organize_dry_run_move_conflict(capsys):
    """--dry-run and --move cannot be used together."""
    result = run(["organize", "/tmp", "--dry-run", "--move"])
    assert result != 0


def test_organize_dry_run_rename_only_conflict(capsys):
    """--dry-run and --rename-only cannot be used together."""
    result = run(["organize", "/tmp", "--dry-run", "--rename-only"])
    assert result != 0


def test_organize_move_rename_only_conflict(capsys):
    """--move and --rename-only cannot be used together."""
    result = run(["organize", "/tmp", "--move", "--rename-only"])
    assert result != 0


def test_organize_inside_library_requires_confirmation(tmp_path, capsys):
    """Organize inside existing library without --yes aborts in non-interactive."""
    from pathlib import Path
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
                    result = run(["enrich", str(lib), "--verbose"])

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
