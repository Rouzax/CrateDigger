"""Tests for per-command file logging in festival_organizer.log."""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
from pathlib import Path
from unittest.mock import patch

from festival_organizer.log import _cleanup_old_logs, setup_logging


def _reset_logger():
    logger = logging.getLogger("festival_organizer")
    for h in list(logger.handlers):
        logger.removeHandler(h)


def _patch_paths(tmp_path):
    """Return a context manager that patches festival_organizer.log.paths for per-command logs."""
    ctx = patch("festival_organizer.log.paths")
    mock_paths = ctx.__enter__()
    mock_paths.log_dir.return_value = tmp_path
    mock_paths.ensure_parent.side_effect = lambda p: (
        p.parent.mkdir(parents=True, exist_ok=True),
        p,
    )[1]
    return ctx, mock_paths


def _find_memory_handler(logger=None):
    """Return the MemoryHandler from the logger, or raise."""
    if logger is None:
        logger = logging.getLogger("festival_organizer")
    for h in logger.handlers:
        if isinstance(h, logging.handlers.MemoryHandler):
            return h
    raise AssertionError("no MemoryHandler found on logger")


def _find_file_handler(logger=None):
    """Return the FileHandler that is the target of the MemoryHandler."""
    mem = _find_memory_handler(logger)
    assert isinstance(mem.target, logging.FileHandler)
    return mem.target


class TestPerCommandFileHandler:
    def test_adds_memory_handler_wrapping_file_handler(self, tmp_path: Path):
        ctx, mock_paths = _patch_paths(tmp_path)
        try:
            _reset_logger()
            setup_logging(verbose=False, debug=False, command="identify")
            mem = _find_memory_handler()
            assert isinstance(mem.target, logging.FileHandler)
            assert "identify-" in os.path.basename(mem.target.baseFilename)
        finally:
            ctx.__exit__(None, None, None)

    def test_default_prefix_when_no_command(self, tmp_path: Path):
        ctx, mock_paths = _patch_paths(tmp_path)
        try:
            _reset_logger()
            setup_logging(verbose=False, debug=False, command="")
            fh = _find_file_handler()
            assert "cratedigger-" in os.path.basename(fh.baseFilename)
        finally:
            ctx.__exit__(None, None, None)

    def test_creates_log_parent_dir(self, tmp_path: Path):
        log_dir = tmp_path / "deep" / "nested"
        ctx = patch("festival_organizer.log.paths")
        mock_paths = ctx.__enter__()
        mock_paths.log_dir.return_value = log_dir
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        try:
            _reset_logger()
            setup_logging(verbose=False, debug=False)
            assert log_dir.is_dir()
        finally:
            ctx.__exit__(None, None, None)

    def test_returns_log_path(self, tmp_path: Path):
        ctx, mock_paths = _patch_paths(tmp_path)
        try:
            _reset_logger()
            result = setup_logging(verbose=False, debug=False, command="enrich")
            assert result is not None
            assert "enrich-" in str(result)
        finally:
            ctx.__exit__(None, None, None)


def test_file_handler_records_debug_even_when_console_is_warning(tmp_path):
    """The per-command log file captures DEBUG events regardless of CLI verbosity."""
    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        log_path = setup_logging(verbose=False, debug=False)

        logger = logging.getLogger("festival_organizer.sample")
        logger.debug("debug-marker")
        logger.info("info-marker")
        logger.warning("warning-marker")

        # Flush the MemoryHandler to push buffered records to the file.
        for handler in logging.getLogger("festival_organizer").handlers:
            handler.flush()

        contents = Path(log_path).read_text(encoding="utf-8")
        assert "debug-marker" in contents
        assert "info-marker" in contents
        assert "warning-marker" in contents
    finally:
        ctx.__exit__(None, None, None)


def test_console_handler_still_respects_cli_verbosity(tmp_path, capsys):
    """Default verbosity keeps DEBUG off the console even though the file is at DEBUG."""
    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=False, debug=False, console=None)

        logger = logging.getLogger("festival_organizer.sample")
        logger.debug("should-not-appear-on-stderr")
        captured = capsys.readouterr()
        assert "should-not-appear-on-stderr" not in captured.err
    finally:
        ctx.__exit__(None, None, None)


def test_repeated_setup_closes_previous_handlers(tmp_path):
    """Re-running setup_logging must close the previous MemoryHandler and its target."""
    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=False, debug=False)

        first_mem = _find_memory_handler()
        first_target = first_mem.target

        # Force a flush so the file handler stream opens.
        logging.getLogger("festival_organizer.sample").warning("open-the-stream")
        assert first_target.stream is not None, (
            "FileHandler stream did not open on flush; test setup is wrong"
        )

        setup_logging(verbose=False, debug=False)

        # The old target FileHandler should have been closed.
        # FileHandler.close() sets self.stream to None.
        assert first_target.stream is None, (
            "previous FileHandler was not closed on re-setup; FD leak on repeated calls"
        )
    finally:
        ctx.__exit__(None, None, None)


def test_file_handler_opens_lazily(tmp_path):
    """delay=True defers opening the log file until the first flush.

    This avoids creating an empty log file for runs that never log
    anything (e.g. ``--version``).
    """
    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=False, debug=False)

        fh = _find_file_handler()
        assert fh.delay is True, "FileHandler should be constructed with delay=True"
        # Stream not yet open because delay=True and nothing was flushed.
        assert fh.stream is None, (
            "with delay=True the stream should stay None until first flush"
        )
    finally:
        ctx.__exit__(None, None, None)


def test_setup_logging_survives_unwritable_log_dir(tmp_path, caplog):
    """Unwritable log path must not crash setup_logging; console handler still works."""
    # Point at a path where ensure_parent cannot create the dir (parent is a file).
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    bad_log_dir = blocker / "subdir"

    with patch("festival_organizer.log.paths") as mock_paths:
        mock_paths.log_dir.return_value = bad_log_dir
        from festival_organizer import paths as real_paths

        mock_paths.ensure_parent.side_effect = real_paths.ensure_parent

        _reset_logger()
        with caplog.at_level("WARNING", logger="festival_organizer"):
            result = setup_logging(verbose=False, debug=False)

    assert result is None
    # Console handler is still present.
    root = logging.getLogger("festival_organizer")
    assert any(not isinstance(h, logging.handlers.MemoryHandler) for h in root.handlers)
    # No MemoryHandler was installed because we could not create the path.
    assert not any(isinstance(h, logging.handlers.MemoryHandler) for h in root.handlers)
    # One WARNING about the disabled log file was emitted.
    assert any(
        "log.file_handler: status=disabled" in rec.getMessage()
        for rec in caplog.records
    )


def test_memory_handler_capacity_and_flush_level(tmp_path):
    """MemoryHandler uses capacity=50 and flushLevel=WARNING."""
    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        setup_logging(verbose=False, debug=False)
        mem = _find_memory_handler()
        assert mem.capacity == 50
        assert mem.flushLevel == logging.WARNING
    finally:
        ctx.__exit__(None, None, None)


def test_file_attribution_appears_in_log_output(tmp_path):
    """ContextVar-based file attribution shows up in the file handler output."""
    from festival_organizer.log import _file_var

    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        log_path = setup_logging(verbose=False, debug=False, command="organize")

        _file_var.set("my-set-recording.mkv")
        logger = logging.getLogger("festival_organizer.sample")
        logger.warning("test-marker")

        for handler in logging.getLogger("festival_organizer").handlers:
            handler.flush()

        contents = Path(log_path).read_text(encoding="utf-8")
        assert "[my-set-recording.mkv]" in contents
    finally:
        _file_var.set("")
        ctx.__exit__(None, None, None)


def test_file_attribution_empty_when_unset(tmp_path):
    """When no file context is active, the bracket field is absent."""
    from festival_organizer.log import _file_var

    ctx, mock_paths = _patch_paths(tmp_path)
    try:
        _reset_logger()
        _file_var.set("")
        log_path = setup_logging(verbose=False, debug=False, command="organize")

        logger = logging.getLogger("festival_organizer.sample")
        logger.warning("no-file-marker")

        for handler in logging.getLogger("festival_organizer").handlers:
            handler.flush()

        contents = Path(log_path).read_text(encoding="utf-8")
        assert "no-file-marker" in contents
        assert "[]" not in contents
    finally:
        ctx.__exit__(None, None, None)


class TestCleanupOldLogs:
    def test_deletes_old_log_files(self, tmp_path: Path):
        old_file = tmp_path / "identify-2026-04-01T10-00-00-abcd.log"
        old_file.write_text("old log data")
        # Set mtime to 10 days ago
        old_mtime = time.time() - 10 * 86400
        os.utime(old_file, (old_mtime, old_mtime))

        recent_file = tmp_path / "enrich-2026-05-06T10-00-00-ef01.log"
        recent_file.write_text("recent log data")

        _cleanup_old_logs(tmp_path, max_age_days=7)

        assert not old_file.exists()
        assert recent_file.exists()

    def test_ignores_non_log_files(self, tmp_path: Path):
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("keep me")
        old_mtime = time.time() - 10 * 86400
        os.utime(txt_file, (old_mtime, old_mtime))

        _cleanup_old_logs(tmp_path, max_age_days=7)

        assert txt_file.exists()

    def test_survives_missing_directory(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist"
        # Should not raise
        _cleanup_old_logs(nonexistent, max_age_days=7)
