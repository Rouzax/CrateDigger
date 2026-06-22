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
    ctx = patch("festival_organizer.log.paths")
    mock_paths = ctx.__enter__()
    mock_paths.log_dir.return_value = tmp_path
    mock_paths.ensure_parent.side_effect = lambda p: (
        p.parent.mkdir(parents=True, exist_ok=True),
        p,
    )[1]
    return ctx, mock_paths


def _console_handler():
    """Return the non-file handler the CLI users see. Assumes setup_logging has run."""
    logger = logging.getLogger("festival_organizer")
    for h in logger.handlers:
        if not isinstance(h, (logging.handlers.MemoryHandler, logging.FileHandler)):
            return h
    raise AssertionError("no console handler found")


def test_setup_logging_default_console_is_warning(tmp_path):
    """Default setup configures the console handler at WARNING."""
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging()
        assert _console_handler().level == logging.WARNING
    finally:
        ctx.__exit__(None, None, None)


def test_setup_logging_verbose_console_is_info(tmp_path):
    """Verbose setup configures the console handler at INFO."""
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=True)
        assert _console_handler().level == logging.INFO
    finally:
        ctx.__exit__(None, None, None)


def test_setup_logging_debug_console_is_debug(tmp_path):
    """Debug setup configures the console handler at DEBUG."""
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(debug=True)
        assert _console_handler().level == logging.DEBUG
    finally:
        ctx.__exit__(None, None, None)


def test_setup_logging_has_handlers(tmp_path):
    """Setup adds both a console handler and a MemoryHandler wrapping a FileHandler."""
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging()
        handlers = logging.getLogger("festival_organizer").handlers
        assert len(handlers) >= 2
        assert any(isinstance(h, logging.handlers.MemoryHandler) for h in handlers)
    finally:
        ctx.__exit__(None, None, None)


def test_urllib3_logger_pinned_to_info(tmp_path):
    """urllib3 DEBUG must not flood the file handler."""
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(debug=True)
        assert logging.getLogger("urllib3").level == logging.INFO
    finally:
        ctx.__exit__(None, None, None)


def test_pil_logger_pinned_to_info(tmp_path):
    """PIL DEBUG must not flood the file handler."""
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(debug=True)
        assert logging.getLogger("PIL").level == logging.INFO
    finally:
        ctx.__exit__(None, None, None)


def test_env_override_sets_console_level(tmp_path, monkeypatch):
    """CRATEDIGGER_LOG_LEVEL overrides the flag-derived console level."""
    monkeypatch.setenv("CRATEDIGGER_LOG_LEVEL", "DEBUG")
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=False, debug=False)
        assert _console_handler().level == logging.DEBUG
    finally:
        ctx.__exit__(None, None, None)


def test_env_override_bad_value_falls_back(tmp_path, monkeypatch):
    """Invalid CRATEDIGGER_LOG_LEVEL falls back to the flag-derived default."""
    monkeypatch.setenv("CRATEDIGGER_LOG_LEVEL", "BOGUS")
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=True)
        assert _console_handler().level == logging.INFO
    finally:
        ctx.__exit__(None, None, None)


def test_env_override_does_not_affect_file_handler(tmp_path, monkeypatch):
    """CRATEDIGGER_LOG_LEVEL must not change the file handler level."""
    monkeypatch.setenv("CRATEDIGGER_LOG_LEVEL", "ERROR")
    ctx, mp = _mock_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging()
        from tests.test_log_file_handler import _find_file_handler

        assert _find_file_handler().level == logging.DEBUG
    finally:
        ctx.__exit__(None, None, None)
