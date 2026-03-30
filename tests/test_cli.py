import logging
from unittest.mock import patch
from festival_organizer.cli import run


def test_run_no_command():
    """No command prints help and returns 1."""
    assert run([]) == 1


def test_run_nonexistent_path():
    """Nonexistent path returns 1 with error message."""
    assert run(["scan", "/nonexistent/path/abc123"]) == 1


def test_run_unexpected_error_returns_1(capsys):
    """Unexpected exception is caught, printed to stderr, returns 1."""
    with patch("festival_organizer.cli.load_config", side_effect=RuntimeError("boom")):
        result = run(["scan", "/tmp"])
    assert result == 1
    captured = capsys.readouterr()
    assert "boom" in captured.err


def test_verbose_flag_enables_info_logging():
    """The --verbose flag enables INFO logging for the package."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.find_library_root", return_value=None):
            run(["scan", "/tmp", "--verbose"])
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.INFO


def test_debug_flag_enables_debug_logging():
    """The --debug flag enables DEBUG logging for the package."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.find_library_root", return_value=None):
            run(["scan", "/tmp", "--debug"])
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.DEBUG


def test_dry_run_is_alias_for_scan():
    """dry-run command produces same behavior as scan."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]) as mock_scan:
        with patch("festival_organizer.cli.find_library_root", return_value=None):
            result = run(["dry-run", "/tmp"])
    assert result == 0
    mock_scan.assert_called_once()


def test_organize_inside_library_requires_confirmation(tmp_path, capsys):
    """Organize inside existing library without --yes aborts in non-interactive."""
    from pathlib import Path
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)

    with patch("festival_organizer.cli.find_library_root", return_value=lib):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = run(["organize", str(lib)])

    assert result == 1
    captured = capsys.readouterr()
    assert "confirmation" in captured.err.lower() or "--yes" in captured.err


def test_organize_inside_library_with_yes_proceeds(tmp_path):
    """Organize inside library with --yes skips confirmation."""
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)

    with patch("festival_organizer.cli.find_library_root", return_value=lib):
        with patch("festival_organizer.cli.scan_folder", return_value=[]):
            result = run(["organize", str(lib), "--yes"])

    assert result == 0


def test_organize_with_explicit_output_no_confirmation(tmp_path):
    """Organize with explicit -o never prompts for confirmation."""
    lib = tmp_path / "concerts"
    (lib / ".cratedigger").mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()

    with patch("festival_organizer.cli.find_library_root", return_value=lib):
        with patch("festival_organizer.cli.scan_folder", return_value=[]):
            result = run(["organize", str(lib), "-o", str(out)])

    assert result == 0
