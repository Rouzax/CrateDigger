"""Logging configuration for CrateDigger.

Logging:
    Logger: 'festival_organizer' (root for all modules)
    Key events:
        - setup (DEBUG): Logger configured with level and handler
    See docs/logging.md for full guidelines.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys

from rich.console import Console
from rich.highlighter import NullHighlighter
from rich.logging import RichHandler

from festival_organizer import paths


def setup_logging(
    verbose: bool = False,
    debug: bool = False,
    console: Console | None = None,
) -> None:
    """Configure the festival_organizer logger.

    Call once at CLI startup. All modules use logging.getLogger(__name__).

    When a Rich Console is provided, logs route through RichHandler on
    stdout so they coordinate with spinners and progress output.
    Without a Console, logs go to stderr via plain StreamHandler.

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

    if console:
        handler = RichHandler(
            console=console,
            show_time=False,
            show_path=False,
            markup=False,
            rich_tracebacks=False,
            highlighter=NullHighlighter(),
        )
        handler.setLevel(level)
        fmt = logging.Formatter("[%(module)s] %(message)s")
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        fmt = logging.Formatter("        %(levelname)s [%(module)s] %(message)s")

    handler.setFormatter(fmt)
    logger.addHandler(handler)

    # Rotating file handler: always active, 5 MB x 5 rotations
    log_path = paths.ensure_parent(paths.log_file())
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    logger.addHandler(file_handler)
