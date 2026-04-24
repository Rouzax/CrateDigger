"""DEBUG-logged wrapper around ``subprocess.run``.

All ``festival_organizer`` subprocess invocations (mkvextract, mkvpropedit,
mediainfo, ffprobe, tool version probes) route through :func:`tracked_run`
so the rotating log file captures the full post-mortem trail: the argv
command, the working directory when set, the exit code, and a stderr tail
on non-zero exits.

Cross-repo note: TrackSplit has a parallel ``tracked_run`` that adds
cancel-event tracking for Ctrl+C in its ``ThreadPoolExecutor`` worker
pool. CrateDigger has no worker pool, so this wrapper intentionally omits
that tracking and stays a thin pass-through to ``subprocess.run``. The
DEBUG log shape (command + returncode + stderr tail) is kept symmetric
with TrackSplit's copy so the rotating logs read the same across repos.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Any

logger = logging.getLogger("festival_organizer.subprocess")

_STDERR_TAIL_CHARS = 500


def _fmt_cmd(cmd: Any) -> str:
    """Render a command list (or string) as a shell-quoted single line."""
    if isinstance(cmd, (list, tuple)):
        return " ".join(shlex.quote(str(a)) for a in cmd)
    return str(cmd)


def _stderr_tail(stderr: Any) -> str:
    """Return the last ``_STDERR_TAIL_CHARS`` chars of stderr, as a string."""
    if stderr is None:
        return ""
    if isinstance(stderr, bytes):
        try:
            stderr = stderr.decode("utf-8", errors="replace")
        except Exception:
            stderr = repr(stderr)
    text = str(stderr).strip()
    if len(text) > _STDERR_TAIL_CHARS:
        return "..." + text[-_STDERR_TAIL_CHARS:]
    return text


def tracked_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a subprocess and log the invocation at DEBUG level.

    Drop-in replacement for :func:`subprocess.run`. All keyword arguments
    are forwarded unchanged. Exceptions propagate to the caller; failures
    are logged at DEBUG before re-raising so the rotating log file sees
    them even when the caller catches and handles silently.

    DEBUG log shape:
      - Before invocation: ``subprocess: <cmd> (cwd=<cwd>)``
        (``cwd`` segment only when ``cwd`` kwarg is set).
      - After invocation: ``subprocess exit <n>: <cmd>`` on success;
        ``subprocess exit <n>: <cmd>; stderr tail: <tail>`` on non-zero.
      - On ``TimeoutExpired``: ``subprocess timed out: <cmd>``.
      - On spawn failure (``OSError``/``SubprocessError``):
        ``subprocess failed to spawn: <cmd>: <exc>``.
    """
    cmd_str = _fmt_cmd(cmd)
    cwd = kwargs.get("cwd")
    if cwd is not None:
        logger.debug("subprocess: %s (cwd=%s)", cmd_str, cwd)
    else:
        logger.debug("subprocess: %s", cmd_str)

    try:
        result = subprocess.run(cmd, **kwargs)
    except subprocess.TimeoutExpired:
        logger.debug("subprocess timed out: %s", cmd_str)
        raise
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("subprocess failed to spawn: %s: %s", cmd_str, e)
        raise

    if result.returncode != 0:
        tail = _stderr_tail(result.stderr)
        if tail:
            logger.debug(
                "subprocess exit %d: %s; stderr tail: %s",
                result.returncode, cmd_str, tail,
            )
        else:
            logger.debug("subprocess exit %d: %s", result.returncode, cmd_str)
    else:
        logger.debug("subprocess exit 0: %s", cmd_str)

    return result
