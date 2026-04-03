"""Kodi JSON-RPC client for library sync.

After enrichment, notifies Kodi to re-read NFO files and artwork for
items that were updated. Uses VideoLibrary.Scan for new files and
VideoLibrary.RefreshMusicVideo for existing items.

Kodi queues RefreshMusicVideo calls internally via CVideoLibraryQueue,
so rapid sequential calls are safe; each refresh is processed in order.

Logging:
    Logger: 'festival_organizer.kodi'
    Key events:
        - sync started (INFO): number of items and Kodi host
        - item refreshed (INFO): per-file confirmation
        - item not found (WARNING): file not in Kodi library
        - connection failed (WARNING): Kodi unreachable
    See docs/logging.md for full guidelines.
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth
from rich.console import Console

logger = logging.getLogger(__name__)


class KodiError(Exception):
    """Raised on Kodi JSON-RPC connection or protocol errors."""


class KodiClient:
    """Thin wrapper around Kodi's JSON-RPC HTTP interface."""

    def __init__(self, host: str, port: int, username: str, password: str):
        self._url = f"http://{host}:{port}/jsonrpc"
        self._session = requests.Session()
        self._session.auth = HTTPBasicAuth(username, password)
        self._request_id = 0

    def _call(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC 2.0 request and return the result."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._request_id,
        }
        if params:
            payload["params"] = params

        logger.debug("JSON-RPC -> %s %s", method, params or {})

        try:
            resp = self._session.post(self._url, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.ConnectionError as e:
            raise KodiError(f"Cannot connect to Kodi at {self._url}: {e}") from e
        except requests.HTTPError as e:
            raise KodiError(f"Kodi HTTP error: {e}") from e
        except requests.Timeout as e:
            raise KodiError(f"Kodi request timed out: {e}") from e

        data = resp.json()
        if "error" in data:
            err = data["error"]
            raise KodiError(f"Kodi RPC error: {err.get('message', err)}")

        logger.debug("JSON-RPC <- %s", data.get("result", ""))
        return data.get("result", {})

    def scan(self, directory: str = "") -> None:
        """Trigger a video library scan (asynchronous in Kodi)."""
        self._call("VideoLibrary.Scan", {
            "directory": directory,
        })
        logger.info("Triggered Kodi library scan")

    def clean(self) -> None:
        """Clean library: remove entries for files that no longer exist."""
        self._call("VideoLibrary.Clean", {
            "content": "musicvideos",
            "showdialogs": False,
        })
        logger.info("Triggered Kodi library clean (musicvideos)")

    def get_music_videos(self) -> dict[str, int]:
        """Fetch all music videos and return {file_path: musicvideoid}.

        Paths are stored exactly as Kodi reports them (e.g. SMB URLs).
        """
        result = self._call("VideoLibrary.GetMusicVideos", {
            "properties": ["file"],
        })
        mapping: dict[str, int] = {}
        for mv in result.get("musicvideos", []):
            file_path = mv.get("file", "")
            mv_id = mv.get("musicvideoid")
            if file_path and mv_id is not None:
                mapping[file_path] = mv_id
        logger.debug("Kodi library contains %d music videos", len(mapping))
        return mapping

    def refresh_music_video(self, musicvideoid: int) -> None:
        """Refresh a single music video (re-reads NFO + clears artwork cache)."""
        self._call("VideoLibrary.RefreshMusicVideo", {
            "musicvideoid": musicvideoid,
            "ignorenfo": False,
        })


def _infer_path_mapping(
    local_paths: list[Path],
    kodi_videos: dict[str, int],
) -> tuple[str, str] | None:
    """Auto-detect the local->kodi prefix mapping by matching filenames.

    Finds a local file whose name appears in a Kodi path, then computes the
    longest common suffix (case-insensitive) between the two paths to derive
    the prefix pair.
    Returns (local_prefix, kodi_prefix) or None if no match is found.
    """
    # Build filename -> kodi_path index (case-insensitive on filename)
    kodi_by_name: dict[str, str] = {}
    for kodi_path in kodi_videos:
        name = kodi_path.rsplit("/", 1)[-1] if "/" in kodi_path else kodi_path
        kodi_by_name[name.lower()] = kodi_path

    for local_path in local_paths:
        kodi_path = kodi_by_name.get(local_path.name.lower())
        if not kodi_path:
            continue

        # Split both paths into parts and find the common suffix
        local_parts = local_path.resolve().parts
        kodi_parts = kodi_path.replace("\\", "/").split("/")

        # Walk backwards, case-insensitive comparison
        common = 0
        for lp, kp in zip(reversed(local_parts), reversed(kodi_parts)):
            if lp.lower() == kp.lower():
                common += 1
            else:
                break

        if common < 1:
            continue

        # local prefix = everything before the common suffix
        local_prefix = str(Path(*local_parts[:len(local_parts) - common]))
        kodi_prefix = "/".join(kodi_parts[:len(kodi_parts) - common])

        logger.info("Auto-detected path mapping: %s -> %s", local_prefix, kodi_prefix)
        return (local_prefix, kodi_prefix)

    return None


def _translate_path(
    local_path: Path,
    local_prefix: str,
    kodi_prefix: str,
    kodi_lookup: dict[str, str],
) -> str | None:
    """Translate a local path to its Kodi equivalent using prefix mapping.

    Uses case-insensitive lookup against actual Kodi paths to handle
    differences like local "Afrojack" vs Kodi "AFROJACK".

    Returns the exact Kodi path string, or None if no match.
    """
    resolved = str(local_path.resolve())
    # Case-insensitive prefix check
    if not resolved.lower().startswith(local_prefix.lower()):
        return None
    relative = resolved[len(local_prefix):]
    relative = relative.replace("\\", "/").lstrip("/")
    if relative:
        candidate = f"{kodi_prefix}/{relative}"
    else:
        candidate = kodi_prefix
    # Look up case-insensitive against actual Kodi paths
    return kodi_lookup.get(candidate.lower())


def sync_library(
    client: KodiClient,
    changed_paths: list[Path],
    console: Console,
    quiet: bool = False,
    path_mapping: dict | None = None,
) -> None:
    """Sync changed files with Kodi: refresh existing, scan for new, clean stale.

    Order: refresh existing items first, then scan for new files, then clean
    stale entries. This avoids the race condition of scanning before the
    library index is fetched.

    Path matching strategy (in order):
    1. Prefix mapping with case-insensitive lookup (explicit config or auto-detected)
    2. Exact path match (same filesystem)
    3. Filename-only fallback (case-insensitive)

    Args:
        path_mapping: Optional dict with "local" and "kodi" keys for path
            translation. If not provided, the mapping is auto-detected.
    """
    if not changed_paths:
        return

    logger.info("Syncing %d updated items with Kodi", len(changed_paths))

    if not quiet:
        console.print()
        console.print("[bold]Kodi sync[/bold]")

    # Build path-to-ID mapping from Kodi's library
    if not quiet:
        with console.status("Fetching Kodi library..."):
            kodi_videos = client.get_music_videos()
    else:
        kodi_videos = client.get_music_videos()

    # Case-insensitive lookup: lowered path -> original Kodi path
    kodi_lower: dict[str, str] = {p.lower(): p for p in kodi_videos}

    # Determine path mapping: explicit config or auto-detect
    local_prefix = ""
    kodi_prefix = ""
    if path_mapping:
        local_prefix = path_mapping.get("local", "")
        kodi_prefix = path_mapping.get("kodi", "")
        if local_prefix and kodi_prefix:
            local_prefix = str(Path(local_prefix).resolve())
            logger.info("Path mapping (config): %s -> %s", local_prefix, kodi_prefix)

    if not (local_prefix and kodi_prefix):
        inferred = _infer_path_mapping(changed_paths, kodi_videos)
        if inferred:
            local_prefix, kodi_prefix = inferred

    # Build a filename-to-ID index as last-resort fallback (case-insensitive)
    filename_index: dict[str, int] = {}
    for kodi_path, mv_id in kodi_videos.items():
        name = kodi_path.rsplit("/", 1)[-1] if "/" in kodi_path else kodi_path
        filename_index[name.lower()] = mv_id

    # Deduplicate paths (album_poster expansion may add duplicates)
    unique_paths = list(dict.fromkeys(changed_paths))

    refreshed = 0
    not_found = 0

    for path in unique_paths:
        mv_id = None

        # Strategy 1: prefix mapping (case-insensitive)
        if local_prefix and kodi_prefix:
            kodi_path = _translate_path(path, local_prefix, kodi_prefix, kodi_lower)
            if kodi_path:
                mv_id = kodi_videos.get(kodi_path)

        # Strategy 2: exact path match (same filesystem)
        if mv_id is None:
            mv_id = kodi_videos.get(str(path.resolve()))

        # Strategy 3: filename match (case-insensitive fallback)
        if mv_id is None:
            mv_id = filename_index.get(path.name.lower())
            if mv_id is not None:
                logger.debug("Matched by filename: %s", path.name)

        if mv_id is not None:
            client.refresh_music_video(mv_id)
            logger.info("Refreshed in Kodi: %s", path.name)
            refreshed += 1
        else:
            logger.warning(
                "Not in Kodi library (will be picked up by scan): %s",
                path.name,
            )
            not_found += 1

    # Per-item results
    if not quiet:
        from rich.text import Text
        text = Text("        ")
        text.append("\u2714  ", style="green")
        text.append(f"refreshed {refreshed}")
        if not_found:
            text.append("  ")
            text.append("\u25cb  ", style="dim")
            text.append(f"{not_found} not yet in library", style="dim")
        console.print(text)

    # Scan for new files, then clean stale entries
    if not quiet:
        with console.status("Scanning for new files..."):
            client.scan()
        with console.status("Cleaning stale entries..."):
            client.clean()
    else:
        client.scan()
        client.clean()
