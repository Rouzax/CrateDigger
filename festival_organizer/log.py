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
        --debug:   console at DEBUG (cache hits, retries, internal mechanics)
        --verbose: console at INFO  (key decisions, downloads, parse results)
        default:   console at WARNING (failures that don't stop the pipeline)

    The rotating log file always captures DEBUG regardless of CLI
    verbosity, so the file is a full post-mortem trail for the run.
    """
    logger = logging.getLogger("festival_organizer")

    # Close existing handlers before clearing so we do not leak file
    # descriptors on repeated calls (tests, subcommand loops). The logging
    # module's logger.handlers.clear() only unlinks the handlers; the
    # underlying streams stay open until we explicitly close them.
    for handler in list(logger.handlers):
        try:
            handler.close()
        except Exception:
            pass
    logger.handlers.clear()

    console_level = logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    # The logger itself must accept the most verbose level any handler wants.
    logger.setLevel(logging.DEBUG)

    if console:
        handler = RichHandler(
            console=console,
            show_time=False,
            show_path=False,
            markup=False,
            rich_tracebacks=False,
            highlighter=NullHighlighter(),
        )
        handler.setLevel(console_level)
        fmt = logging.Formatter("[%(module)s] %(message)s")
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(console_level)
        fmt = logging.Formatter("        %(levelname)s [%(module)s] %(message)s")

    handler.setFormatter(fmt)
    logger.addHandler(handler)

    # Rotating file handler: always active at DEBUG so the log file is a
    # full post-mortem trail regardless of the CLI verbosity chosen for
    # this run. delay=True defers opening the file until the first emit,
    # narrowing cross-process contention and avoiding empty log files for
    # silent runs (see Task 7). If the log directory cannot be created
    # or opened (read-only mount, permissions, quota), fall back to
    # console-only and emit a single WARNING.
    try:
        log_path = paths.ensure_parent(paths.log_file())
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning(
            "Rotating log file disabled (%s): %s",
            paths.log_file(), exc,
        )
