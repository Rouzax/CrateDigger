"""Startup update-notification check for CrateDigger.

Hand-synced with src/tracksplit/update_check.py in the TrackSplit repo.
Keep in sync when editing. Only PACKAGE_NAME, ENV_VAR, and REPO_URL differ.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

PACKAGE_NAME = "cratedigger"
ENV_VAR = "CRATEDIGGER_NO_UPDATE_CHECK"
REPO_URL = "https://github.com/Rouzax/CrateDigger"

SCHEMA_VERSION = 1
_CACHE_FILENAME = "update-check.json"

_RELEASES_URL_TEMPLATE = "https://api.github.com/repos/{owner_repo}/releases/latest"
_HTTP_TIMEOUT_SECONDS = 2.0

_TRUTHY = {"1", "true", "yes"}

_SUCCESS_TTL_SECONDS = 86400
_FAILURE_TTL_SECONDS = 3600

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PRERELEASE_RE = re.compile(r"(a|b|rc|dev|post)", re.IGNORECASE)


def _parse_version(s: str) -> tuple[int, int, int] | None:
    m = _VERSION_RE.match(s.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _is_newer(installed: str, candidate: str) -> bool:
    a = _parse_version(installed)
    b = _parse_version(candidate)
    if a is None or b is None:
        return False
    return b > a


def _is_prerelease_string(v: str) -> bool:
    return bool(_PRERELEASE_RE.search(v))


def _cache_path() -> Path:
    """Return the OS-appropriate path for the cache file."""
    if win := os.environ.get("LOCALAPPDATA"):
        return Path(win) / PACKAGE_NAME / _CACHE_FILENAME
    if xdg := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg) / PACKAGE_NAME / _CACHE_FILENAME
    return Path.home() / ".cache" / PACKAGE_NAME / _CACHE_FILENAME


def _read_cache() -> dict | None:
    """Return the cached entry dict, or None if missing/corrupt/unknown-schema."""
    p = _cache_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION:
        return None
    return data


def _cache_is_fresh(entry: dict) -> bool:
    """Return True iff the cache entry has not yet expired."""
    checked_at = entry.get("checked_at")
    ttl = entry.get("ttl_seconds")
    if checked_at is None or ttl is None:
        return False
    return (time.time() - checked_at) < ttl


def _write_cache(*, latest_version: str | None, ttl_seconds: int) -> None:
    """Atomically write a fresh cache entry."""
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA_VERSION,
        "checked_at": int(time.time()),
        "ttl_seconds": ttl_seconds,
        "latest_version": latest_version,
    }
    fd, tmp_path = tempfile.mkstemp(
        dir=str(p.parent),
        prefix=p.name + ".",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, p)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _upgrade_command() -> str:
    prefix = sys.prefix.replace("\\", "/")
    if "PIPX_HOME" in os.environ or "/pipx/venvs/" in prefix:
        return f"pipx upgrade {PACKAGE_NAME}"
    if "/uv/tools/" in prefix:
        return f"uv tool upgrade {PACKAGE_NAME}"
    return f"pip install --upgrade git+{REPO_URL}.git"


def _is_suppressed() -> bool:
    """Return True if the update check should be skipped entirely."""
    if os.environ.get(ENV_VAR, "").strip().lower() in _TRUTHY:
        return True
    try:
        if not sys.stdout.isatty():
            return True
    except (AttributeError, ValueError):
        return True
    return False


def _releases_url() -> str:
    owner_repo = REPO_URL.rsplit("github.com/", 1)[-1].rstrip("/")
    return _RELEASES_URL_TEMPLATE.format(owner_repo=owner_repo)


def _user_agent() -> str:
    try:
        from importlib.metadata import version
        return f"{PACKAGE_NAME}/{version(PACKAGE_NAME)} (+update-check)"
    except Exception:
        return f"{PACKAGE_NAME}/unknown (+update-check)"


def _fetch_latest_release() -> str | None:
    """Return the latest stable release version string, or None on any failure."""
    try:
        req = Request(_releases_url(), headers={"User-Agent": _user_agent()})
        with urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not tag:
        return None

    if tag.startswith("v"):
        tag = tag[1:]

    if _is_prerelease_string(tag):
        return None
    if _parse_version(tag) is None:
        return None
    return tag


def print_cached_update_notice(console) -> None:
    """Called at CLI startup. Prints a notice if the cache indicates a
    newer release is available. No network I/O. Silent on any failure."""
    try:
        if _is_suppressed():
            return
        entry = _read_cache()
        if entry is None:
            return
        latest = entry.get("latest_version")
        if not isinstance(latest, str) or not latest:
            return
        try:
            installed = importlib.metadata.version(PACKAGE_NAME)
        except importlib.metadata.PackageNotFoundError:
            return
        if not _is_newer(installed=installed, candidate=latest):
            return
        cmd = _upgrade_command()
        console.print(
            f"[yellow]![/yellow] A new {PACKAGE_NAME} version is available: "
            f"{installed} \u2192 {latest}"
        )
        console.print(f"  Upgrade: [cyan]{cmd}[/cyan]")
    except BaseException:
        import logging
        logging.getLogger(__name__).debug("update-check notice failed", exc_info=True)


def refresh_update_cache() -> None:
    """Called at CLI exit. Refreshes the cache by hitting the GitHub
    Releases API if the cache is stale. Silent on any failure."""
    try:
        if _is_suppressed():
            return
        entry = _read_cache()
        if entry is not None and _cache_is_fresh(entry):
            return
        latest = _fetch_latest_release()
        ttl = _SUCCESS_TTL_SECONDS if latest is not None else _FAILURE_TTL_SECONDS
        _write_cache(latest_version=latest, ttl_seconds=ttl)
    except BaseException:
        import logging
        logging.getLogger(__name__).debug("update-check refresh failed", exc_info=True)
