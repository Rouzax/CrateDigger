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


def test_verbose_flag_enables_debug_logging():
    """The --verbose flag enables DEBUG logging for the package."""
    with patch("festival_organizer.cli.scan_folder", return_value=[]):
        with patch("festival_organizer.cli.find_library_root", return_value=None):
            run(["scan", "/tmp", "--verbose"])
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.DEBUG
