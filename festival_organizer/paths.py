"""Platform-dependent path resolution for CrateDigger.

Every config, cache, state, curated-data, and log path goes through this
module. Nothing else should call ``platformdirs`` directly or compute paths
under ``%APPDATA%``, ``$XDG_*``, or ``~/.cratedigger``.

Layout (Windows / Linux):

- Config + user data (visible):
      ``<Documents>\\CrateDigger\\`` / ``$HOME/CrateDigger/``
      Holds config.toml, festivals.json, artists.json, artist_mbids.json,
      and the user-global festivals/{Name}/logo.* folders. Kept visible on
      purpose so users can edit, add, and back up without knowing where
      ``%APPDATA%`` is.
- Caches (disposable):
      ``%LOCALAPPDATA%\\CrateDigger\\Cache\\`` / ``~/.cache/CrateDigger/``
- State (cookies etc.):
      ``%LOCALAPPDATA%\\CrateDigger\\State\\`` / ``~/.local/state/CrateDigger/``
- Logs:
      ``%LOCALAPPDATA%\\CrateDigger\\Logs\\`` / ``~/.local/state/CrateDigger/log/``

Windows roaming: the visible data folder lives under the user's Documents
folder. Whether it roams depends on Folder Redirection (typical in AD
setups) or OneDrive sync, not on the Roaming Profile mechanism. Caches
intentionally stay local.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path

import platformdirs

APP_NAME = "CrateDigger"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 _()&.\-]")

_LEGACY_STAMP_NAME = "legacy-warning.stamp"

_warned_source_checkout: bool = False


def data_dir() -> Path:
    """Return the visible user data directory.

    Holds config.toml, festivals.json, artists.json, artist_mbids.json, and
    the user-global festivals/{Name}/logo.* subfolders.

    Honors ``$CRATEDIGGER_DATA_DIR`` when set and pointing at an existing
    directory, so CrateDigger and TrackSplit agree on where shared curated
    data lives. When the env var is unset, empty, or points somewhere that
    is not a directory, falls back to the platform default:

    - Windows: ``<Documents>\\CrateDigger`` (discoverable via Explorer).
    - Linux/other: ``$HOME/CrateDigger`` (visible at the top of the home dir).
    """
    env = os.environ.get("CRATEDIGGER_DATA_DIR")
    if env:
        env_path = Path(env)
        if env_path.is_dir():
            return env_path
    if sys.platform == "win32":
        return Path(platformdirs.user_documents_dir()) / APP_NAME
    return Path.home() / APP_NAME


def config_file() -> Path:
    """Return the path to the user config file (``config.toml``)."""
    return data_dir() / "config.toml"


def cache_dir() -> Path:
    """Return the user cache directory (MBID/DJ/source/update caches, artwork)."""
    return Path(platformdirs.user_cache_dir(APP_NAME, appauthor=False))


def state_dir() -> Path:
    """Return the user state directory (1001TL cookies, non-disposable state)."""
    return Path(platformdirs.user_state_dir(APP_NAME, appauthor=False))


def log_file() -> Path:
    """Return the path to the rotating log file (``cratedigger.log``)."""
    return Path(platformdirs.user_log_dir(APP_NAME, appauthor=False)) / "cratedigger.log"


def festivals_file() -> Path:
    """Return the user-curated festivals.json path."""
    return data_dir() / "festivals.json"


def artists_file() -> Path:
    """Return the user-curated artists.json path."""
    return data_dir() / "artists.json"


def artist_mbids_file() -> Path:
    """Return the user-curated artist_mbids.json override path."""
    return data_dir() / "artist_mbids.json"


def festivals_logo_dir() -> Path:
    """Return the user-global curated festival logos directory.

    Library-local logos at ``{library}/.cratedigger/festivals/`` still
    win over this directory when both contain a logo for the same festival.
    """
    return data_dir() / "festivals"


def cookies_file() -> Path:
    """Return the 1001TL session cookies path (inside state_dir)."""
    return state_dir() / "1001tl-cookies.json"


def _safe_artist_name(name: str) -> str:
    """Sanitize an artist name for use as a directory name."""
    return _SAFE_NAME_RE.sub("_", name).strip() or "_"


def artist_cache_dir(artist_name: str) -> Path:
    """Return the per-artist artwork cache directory under cache_dir()."""
    return cache_dir() / "artists" / _safe_artist_name(artist_name)


def ensure_parent(path: Path) -> Path:
    """Create ``path.parent`` if missing. Returns ``path`` unchanged."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _legacy_paths_present(home: Path | None = None) -> list[Path]:
    """Return legacy CrateDigger paths still in use. For the one-time warning."""
    if home is None:
        home = Path.home()
    legacy: list[Path] = []
    old_home = home / ".cratedigger"
    if old_home.is_dir():
        legacy.append(old_home)
    old_cookies = home / ".1001tl-cookies.json"
    if old_cookies.is_file():
        legacy.append(old_cookies)
    return legacy


def warn_if_legacy_paths_exist(home: Path | None = None) -> None:
    """Log a WARNING at most once per day if legacy CrateDigger paths are found.

    Called at CLI startup. No data is moved; this is a nudge to migrate.

    Suppression uses an ISO-date stamp file at
    ``state_dir() / "legacy-warning.stamp"``. First call on a given day emits
    the WARNING and writes today's date. Subsequent calls the same day stay
    silent. A stamp dated today or later (clock skew, manual edit) suppresses;
    a corrupt or unparseable stamp behaves as if absent and is overwritten.
    """
    legacy = _legacy_paths_present(home=home)
    if not legacy:
        return
    if _legacy_stamp_is_fresh():
        return
    logger = logging.getLogger("festival_organizer.paths")
    pretty = "\n  - ".join(str(p) for p in legacy)
    logger.warning(
        "Legacy CrateDigger files detected at old locations:\n  - %s\n"
        "These are no longer read. Move contents to the new platformdirs "
        "locations (see docs/configuration.md) or delete them.",
        pretty,
    )
    _write_legacy_stamp()


def _legacy_stamp_path() -> Path:
    return state_dir() / _LEGACY_STAMP_NAME


def _legacy_stamp_is_fresh() -> bool:
    """Return True iff the stamp file contains today's ISO date or a later one."""
    try:
        content = _legacy_stamp_path().read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return False
    try:
        stamped = date.fromisoformat(content)
    except ValueError:
        return False
    return stamped >= date.today()


def _write_legacy_stamp() -> None:
    """Atomically write today's ISO date to the stamp file. Silent on failure."""
    logger = logging.getLogger("festival_organizer.paths")
    target = _legacy_stamp_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(date.today().isoformat())
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as e:
        logger.debug("Failed to write legacy-warning stamp at %s: %s", target, e)


def _is_source_checkout_dir(path: Path) -> bool:
    """Return True iff ``path`` looks like a CrateDigger source checkout.

    Detection: ``path / "pyproject.toml"`` exists and parses as TOML with
    ``[project].name`` equal to ``"cratedigger"`` (case-insensitive). Any
    read/parse failure returns False, so this helper never raises.
    """
    try:
        with open(path / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    project = data.get("project")
    if not isinstance(project, dict):
        return False
    name = project.get("name")
    if not isinstance(name, str):
        return False
    return name.strip().lower() == "cratedigger"


def warn_if_data_dir_is_source_checkout() -> None:
    """Log a single WARNING per process if ``data_dir()`` resolves inside a
    CrateDigger source checkout.

    A user who clones CrateDigger to ``~/CrateDigger/`` on Linux (or into
    ``<Documents>\\CrateDigger`` on Windows) ends up with the documented data
    directory pointing at the repo root. Any curated file they create at that
    root (e.g. ``artists.json`` for local dev) would then be read as if it were
    real user data. This warning nudges them to set ``CRATEDIGGER_DATA_DIR``.

    If ``CRATEDIGGER_DATA_DIR`` is already set, the user is driving explicitly
    and no warning is emitted.
    """
    global _warned_source_checkout
    if _warned_source_checkout:
        return
    if os.environ.get("CRATEDIGGER_DATA_DIR"):
        return
    resolved = data_dir()
    if not _is_source_checkout_dir(resolved):
        return
    _warned_source_checkout = True
    logger = logging.getLogger("festival_organizer.paths")
    logger.warning(
        "Data directory %s looks like a CrateDigger source checkout "
        "(pyproject.toml found with project name 'cratedigger'). Files "
        "placed at the repo root may be read as curated user data. "
        "Set CRATEDIGGER_DATA_DIR to a dedicated user-data folder to "
        "silence this warning.",
        resolved,
    )
