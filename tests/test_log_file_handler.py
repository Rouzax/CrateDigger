"""Tests for rotating file logging in festival_organizer.log."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from unittest.mock import patch

from festival_organizer.log import setup_logging


def _reset_logger():
    logger = logging.getLogger("festival_organizer")
    for h in list(logger.handlers):
        logger.removeHandler(h)


class TestRotatingFileHandler:
    def test_adds_rotating_file_handler(self, tmp_path: Path):
        log_path = tmp_path / "cratedigger.log"
        with patch("festival_organizer.log.paths") as mock_paths:
            mock_paths.log_file.return_value = log_path
            mock_paths.ensure_parent.side_effect = lambda p: (
                p.parent.mkdir(parents=True, exist_ok=True),
                p,
            )[1]
            _reset_logger()
            setup_logging(verbose=False, debug=False)
            handlers = logging.getLogger("festival_organizer").handlers
            rot = [h for h in handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
            assert len(rot) == 1
            assert rot[0].baseFilename == str(log_path)
            assert rot[0].maxBytes == 5 * 1024 * 1024
            assert rot[0].backupCount == 5

    def test_creates_log_parent_dir(self, tmp_path: Path):
        log_path = tmp_path / "deep" / "nested" / "cratedigger.log"
        with patch("festival_organizer.log.paths") as mock_paths:
            mock_paths.log_file.return_value = log_path
            mock_paths.ensure_parent.side_effect = lambda p: (
                p.parent.mkdir(parents=True, exist_ok=True),
                p,
            )[1]
            _reset_logger()
            setup_logging(verbose=False, debug=False)
            assert log_path.parent.is_dir()


def test_file_handler_records_debug_even_when_console_is_warning(tmp_path):
    """The rotating log file captures DEBUG events regardless of CLI verbosity."""
    log_path = tmp_path / "cratedigger.log"
    with patch("festival_organizer.log.paths") as mock_paths:
        mock_paths.log_file.return_value = log_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        _reset_logger()
        setup_logging(verbose=False, debug=False)

        logger = logging.getLogger("festival_organizer.sample")
        logger.debug("debug-marker")
        logger.info("info-marker")
        logger.warning("warning-marker")

        for handler in logging.getLogger("festival_organizer").handlers:
            handler.flush()

        contents = log_path.read_text(encoding="utf-8")
        assert "debug-marker" in contents
        assert "info-marker" in contents
        assert "warning-marker" in contents


def test_console_handler_still_respects_cli_verbosity(tmp_path, capsys):
    """Default verbosity keeps DEBUG off the console even though the file is at DEBUG."""
    log_path = tmp_path / "cratedigger.log"
    with patch("festival_organizer.log.paths") as mock_paths:
        mock_paths.log_file.return_value = log_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        _reset_logger()
        setup_logging(verbose=False, debug=False, console=None)

        logger = logging.getLogger("festival_organizer.sample")
        logger.debug("should-not-appear-on-stderr")
        captured = capsys.readouterr()
        assert "should-not-appear-on-stderr" not in captured.err


def test_repeated_setup_closes_previous_file_handlers(tmp_path):
    """Re-running setup_logging must close the previous file handler to avoid FD leaks.

    With delay=True, the RotatingFileHandler stream only opens when the first
    record is emitted. Emit one record here so the stream is actually open;
    only then does the stream-is-None assertion after the second setup_logging
    genuinely prove close() ran, rather than trivially holding because the
    stream was never opened.
    """
    log_path = tmp_path / "cratedigger.log"
    with patch("festival_organizer.log.paths") as mock_paths:
        mock_paths.log_file.return_value = log_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        _reset_logger()
        setup_logging(verbose=False, debug=False)

        first_file_handlers = [
            h for h in logging.getLogger("festival_organizer").handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(first_file_handlers) == 1
        first = first_file_handlers[0]

        # Force the lazy stream open so the close-on-resetup assertion below
        # has something to assert against.
        logging.getLogger("festival_organizer.sample").warning("open-the-stream")
        assert first.stream is not None, (
            "RotatingFileHandler stream did not open on emit; test setup is wrong"
        )

        setup_logging(verbose=False, debug=False)

        # The old handler should have been closed before the clear.
        # RotatingFileHandler.close() sets self.stream to None.
        assert first.stream is None, (
            "previous RotatingFileHandler was not closed on re-setup; "
            "FD leak on repeated calls"
        )


def test_file_handler_opens_lazily(tmp_path):
    """delay=True defers opening the log file until the first emit.

    Narrows the cross-process contention window when two CrateDigger
    processes start simultaneously and avoids creating an empty log file
    for runs that never log anything (e.g. `--version`). TrackSplit uses
    the same pattern.
    """
    log_path = tmp_path / "cratedigger.log"
    with patch("festival_organizer.log.paths") as mock_paths:
        mock_paths.log_file.return_value = log_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        _reset_logger()
        setup_logging(verbose=False, debug=False)

        rot = next(
            h for h in logging.getLogger("festival_organizer").handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        )
        assert rot.delay is True, (
            "RotatingFileHandler should be constructed with delay=True; "
            "see docs/faq.md concurrency caveat"
        )
        # Stream not yet open because delay=True and nothing was logged.
        assert rot.stream is None, (
            "with delay=True the stream should stay None until first emit"
        )
