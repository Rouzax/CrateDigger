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
