# tests/test_log.py
import logging
import logging.handlers
from festival_organizer.log import setup_logging


def _console_handler():
    """Return the non-file handler the CLI users see. Assumes setup_logging has run."""
    logger = logging.getLogger("festival_organizer")
    for h in logger.handlers:
        if not isinstance(h, logging.handlers.RotatingFileHandler):
            return h
    raise AssertionError("no console handler found")


def test_setup_logging_default_console_is_warning():
    """Default setup configures the console handler at WARNING."""
    setup_logging()
    assert _console_handler().level == logging.WARNING


def test_setup_logging_verbose_console_is_info():
    """Verbose setup configures the console handler at INFO."""
    setup_logging(verbose=True)
    assert _console_handler().level == logging.INFO


def test_setup_logging_debug_console_is_debug():
    """Debug setup configures the console handler at DEBUG."""
    setup_logging(debug=True)
    assert _console_handler().level == logging.DEBUG


def test_setup_logging_has_handlers():
    """Setup adds both a console handler and a rotating file handler."""
    setup_logging()
    handlers = logging.getLogger("festival_organizer").handlers
    assert len(handlers) >= 2
    assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers)
