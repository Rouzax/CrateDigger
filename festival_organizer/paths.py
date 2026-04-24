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
from pathlib import Path

import platformdirs

APP_NAME = "CrateDigger"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 _()&.\-]")


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
    """Log a single WARNING if legacy CrateDigger paths are found.

    Called once at CLI startup. No data is moved; this is a nudge to migrate.
    """
    legacy = _legacy_paths_present(home=home)
    if not legacy:
        return
    logger = logging.getLogger("festival_organizer.paths")
    pretty = "\n  - ".join(str(p) for p in legacy)
    logger.warning(
        "Legacy CrateDigger files detected at old locations:\n  - %s\n"
        "These are no longer read. Move contents to the new platformdirs "
        "locations (see docs/configuration.md) or delete them.",
        pretty,
    )
