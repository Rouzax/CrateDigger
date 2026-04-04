import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from festival_organizer.cli import run, _analyse_parallel
from festival_organizer.config import Config
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
