"""Logging configuration for CrateDigger."""
import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """Configure the festival_organizer logger.

    Call once at CLI startup. All modules use logging.getLogger(__name__).
    """
    logger = logging.getLogger("festival_organizer")
    # Remove existing handlers to avoid duplicates on repeated calls
    logger.handlers.clear()

    level = logging.DEBUG if verbose else logging.WARNING
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    fmt = logging.Formatter("%(levelname)s: %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
