"""Logging configuration for CrateDigger.

Logging:
    Logger: 'festival_organizer' (root for all modules)
    Key events:
        - setup (DEBUG): Logger configured with level and handler
    See docs/logging.md for full guidelines.
"""
import logging
import sys


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure the festival_organizer logger.

    Call once at CLI startup. All modules use logging.getLogger(__name__).

    Levels:
        --debug:   DEBUG (cache hits, retries, internal mechanics)
        --verbose: INFO  (key decisions, downloads, parse results)
        default:   WARNING (failures that don't stop the pipeline)
    """
    logger = logging.getLogger("festival_organizer")
    # Remove existing handlers to avoid duplicates on repeated calls
    logger.handlers.clear()

    level = logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    fmt = logging.Formatter("        %(levelname)s [%(module)s] %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)
