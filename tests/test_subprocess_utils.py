"""Tests for the tracked_run subprocess wrapper."""
from __future__ import annotations

import logging
import subprocess
import sys

import pytest

from festival_organizer.subprocess_utils import tracked_run


def test_tracked_run_logs_command_and_zero_exit(caplog):
    """Successful run emits DEBUG with command and exit 0."""
    cmd = [sys.executable, "-c", "pass"]
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.subprocess"):
        result = tracked_run(cmd, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert any(sys.executable in rec.message for rec in caplog.records)
    assert any("exit 0" in rec.message for rec in caplog.records)


def test_tracked_run_logs_stderr_tail_on_nonzero(caplog):
    """Non-zero exit emits DEBUG with returncode and stderr tail."""
    cmd = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('boom-distinct-marker'); sys.exit(3)",
    ]
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.subprocess"):
        result = tracked_run(cmd, capture_output=True, text=True, timeout=10)
    assert result.returncode == 3
    joined = "\n".join(rec.message for rec in caplog.records)
    assert "exit 3" in joined
    assert "boom-distinct-marker" in joined


def test_tracked_run_logs_timeout(caplog):
    """TimeoutExpired is logged at DEBUG before re-raising."""
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.subprocess"):
        with pytest.raises(subprocess.TimeoutExpired):
            tracked_run(cmd, capture_output=True, text=True, timeout=0.2)
    assert any("timed out" in rec.message for rec in caplog.records)


def test_tracked_run_logs_spawn_failure(caplog):
    """OSError on spawn (missing binary) is logged at DEBUG before re-raising."""
    cmd = ["/nonexistent/path/that/does/not/exist-xyz123"]
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.subprocess"):
        with pytest.raises((OSError, FileNotFoundError)):
            tracked_run(cmd, capture_output=True, text=True, timeout=10)
    assert any("failed to spawn" in rec.message for rec in caplog.records)


def test_tracked_run_passes_through_kwargs(tmp_path, caplog):
    """The wrapper forwards arbitrary subprocess.run kwargs (cwd, input)."""
    cmd = [sys.executable, "-c", "import os, sys; sys.stdout.write(os.getcwd())"]
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.subprocess"):
        result = tracked_run(
            cmd, capture_output=True, text=True, timeout=10, cwd=str(tmp_path)
        )
    assert result.returncode == 0
    assert str(tmp_path) in result.stdout
