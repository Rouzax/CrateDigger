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
import os
import sys
import time
from contextvars import ContextVar
from datetime import datetime

from rich.console import Console
from rich.highlighter import NullHighlighter
from rich.logging import RichHandler

from festival_organizer import paths

_file_var: ContextVar[str] = ContextVar("_file_var", default="")


class _FileAttributionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        val = _file_var.get()
        record.file = f" [{val}]" if val else ""  # type: ignore[attr-defined]
        return True


def _cleanup_old_logs(log_directory: os.PathLike, max_age_days: int = 7) -> None:
    """Delete ``.log`` files older than *max_age_days* from *log_directory*.

    Silently ignores missing directories and permission errors so startup
    is never blocked by stale log cleanup.
    """
    try:
        cutoff = time.time() - max_age_days * 86400
        with os.scandir(log_directory) as entries:
            for entry in entries:
                if entry.name.endswith(".log") and entry.is_file(follow_symlinks=False):
                    try:
                        if entry.stat().st_mtime < cutoff:
                            os.unlink(entry.path)
                    except OSError:
                        pass
    except OSError:
        pass


def setup_logging(
    verbose: bool = False,
    debug: bool = False,
    console: Console | None = None,
    command: str = "",
) -> os.PathLike[str] | None:
    """Configure the festival_organizer logger.

    Call once at CLI startup. All modules use logging.getLogger(__name__).

    When a Rich Console is provided, logs route through RichHandler on
    stdout so they coordinate with spinners and progress output.
    Without a Console, logs go to stderr via plain StreamHandler.

    Levels:
        --debug:   console at DEBUG (cache hits, retries, internal mechanics)
        --verbose: console at INFO  (key decisions, downloads, parse results)
        default:   console at WARNING (failures that don't stop the pipeline)

    The per-command log file always captures DEBUG regardless of CLI
    verbosity, so the file is a full post-mortem trail for the run.

    Returns the log file path on success, or ``None`` when file logging
    could not be set up (unwritable directory, permissions, etc.).
    """
    logger = logging.getLogger("festival_organizer")

    # Close existing handlers before clearing so we do not leak file
    # descriptors on repeated calls (tests, subcommand loops). The logging
    # module's logger.handlers.clear() only unlinks the handlers; the
    # underlying streams stay open until we explicitly close them.
    for handler in list(logger.handlers):
        try:
            # MemoryHandler.close() flushes buffered records but does not
            # close its target FileHandler. Close the target explicitly so
            # we do not leak file descriptors on repeated calls.
            if isinstance(handler, logging.handlers.MemoryHandler) and handler.target:
                handler.target.close()
            handler.close()
        except Exception:
            pass
    logger.handlers.clear()

    console_level = (
        logging.DEBUG if debug else logging.INFO if verbose else logging.WARNING
    )
    env_level = os.environ.get("CRATEDIGGER_LOG_LEVEL", "").strip().upper()
    if env_level:
        numeric = getattr(logging, env_level, None)
        if isinstance(numeric, int):
            console_level = numeric
    # The logger itself must accept the most verbose level any handler wants.
    logger.setLevel(logging.DEBUG)

    # Pin noisy third-party loggers so they never flood the file handler.
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("PIL").setLevel(logging.INFO)

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

    # Per-command log file: always active at DEBUG so the log file is a
    # full post-mortem trail regardless of the CLI verbosity chosen for
    # this run. A MemoryHandler buffers up to 50 records, flushing
    # immediately on WARNING or above, and on close. delay=True defers
    # opening the file until the first flush, avoiding empty log files
    # for silent runs (e.g. `--version`).
    log_path = None
    try:
        log_directory = paths.log_dir()
        _cleanup_old_logs(log_directory)

        prefix = command if command else "cratedigger"
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        suffix = os.urandom(2).hex()
        filename = f"{prefix}-{stamp}-{suffix}.log"
        log_path = paths.ensure_parent(log_directory / filename)

        file_handler = logging.FileHandler(
            log_path,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.addFilter(_FileAttributionFilter())
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s%(file)s: %(message)s")
        )

        memory_handler = logging.handlers.MemoryHandler(
            capacity=50,
            flushLevel=logging.WARNING,
            target=file_handler,
            flushOnClose=True,
        )
        logger.addHandler(memory_handler)
    except OSError as exc:
        log_path = None
        logger.warning(
            'log.file_handler: status=disabled dir=%s error="%s"',
            paths.log_dir(),
            exc,
        )

    return log_path
