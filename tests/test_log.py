# tests/test_log.py
import logging
from festival_organizer.log import setup_logging


def test_setup_logging_default():
    """Default setup configures WARNING level."""
    setup_logging()
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.WARNING


def test_setup_logging_verbose():
    """Verbose setup configures INFO level."""
    setup_logging(verbose=True)
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.INFO


def test_setup_logging_debug():
    """Debug setup configures DEBUG level."""
    setup_logging(debug=True)
    logger = logging.getLogger("festival_organizer")
    assert logger.level == logging.DEBUG


def test_setup_logging_has_handler():
    """Setup adds a stderr handler."""
    setup_logging()
    logger = logging.getLogger("festival_organizer")
    assert len(logger.handlers) >= 1
