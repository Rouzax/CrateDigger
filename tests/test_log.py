# tests/test_log.py
import logging
import logging.handlers
from unittest.mock import patch

from festival_organizer.log import setup_logging


def _reset_logger():
    logger = logging.getLogger("festival_organizer")
    for h in list(logger.handlers):
        logger.removeHandler(h)


def _mock_paths(tmp_path):
    """Return a context manager that patches festival_organizer.log.paths."""
    log_path = tmp_path / "cratedigger.log"
    ctx = patch("festival_organizer.log.paths")
    mock_paths = ctx.__enter__()
    mock_paths.log_file.return_value = log_path
    mock_paths.ensure_parent.side_effect = lambda p: (
        p.parent.mkdir(parents=True, exist_ok=True),
        p,
    )[1]
    return ctx, mock_paths


def _console_handler():
    """Return the non-file handler the CLI users see. Assumes setup_logging has run."""
    logger = logging.getLogger("festival_organizer")
    for h in logger.handlers:
        if not isinstance(h, logging.handlers.RotatingFileHandler):
            return h
    raise AssertionError("no console handler found")


def test_setup_logging_default_console_is_warning(tmp_path):
    """Default setup configures the console handler at WARNING."""
    with patch("festival_organizer.log.paths") as mp:
        mp.log_file.return_value = tmp_path / "cratedigger.log"
        mp.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True), p)[1]
        _reset_logger()
        setup_logging()
    assert _console_handler().level == logging.WARNING


def test_setup_logging_verbose_console_is_info(tmp_path):
    """Verbose setup configures the console handler at INFO."""
    with patch("festival_organizer.log.paths") as mp:
        mp.log_file.return_value = tmp_path / "cratedigger.log"
        mp.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True), p)[1]
        _reset_logger()
        setup_logging(verbose=True)
    assert _console_handler().level == logging.INFO


def test_setup_logging_debug_console_is_debug(tmp_path):
    """Debug setup configures the console handler at DEBUG."""
    with patch("festival_organizer.log.paths") as mp:
        mp.log_file.return_value = tmp_path / "cratedigger.log"
        mp.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True), p)[1]
        _reset_logger()
        setup_logging(debug=True)
    assert _console_handler().level == logging.DEBUG


def test_setup_logging_has_handlers(tmp_path):
    """Setup adds both a console handler and a rotating file handler."""
    with patch("festival_organizer.log.paths") as mp:
        mp.log_file.return_value = tmp_path / "cratedigger.log"
        mp.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True), p)[1]
        _reset_logger()
        setup_logging()
    handlers = logging.getLogger("festival_organizer").handlers
    assert len(handlers) >= 2
    assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers)
