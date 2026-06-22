"""Kodi JSON-RPC client for library sync.

After enrichment, notifies Kodi to re-read NFO files and artwork for
items that were updated. Uses VideoLibrary.Scan for new files and
VideoLibrary.RefreshMusicVideo for existing items.

Refresh calls are throttled (100ms between each) to avoid overwhelming
Kodi's internal queue. Texture cache entries are hard-deleted before
refresh so Kodi re-fetches artwork immediately.

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

    def _call(
        self, method: str, params: dict | None = None, quiet: bool = False
    ) -> dict:
        """Send a JSON-RPC 2.0 request and return the result."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._request_id,
        }
        if params:
            payload["params"] = params

        if not quiet:
            logger.debug(
                "kodi.rpc: direction=send method=%s params=%s", method, params or {}
            )

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

        if not quiet:
            logger.debug("kodi.rpc: direction=recv result=%s", data.get("result", ""))
        return data.get("result", {})

    def scan(self, directory: str = "") -> None:
        """Trigger a video library scan (asynchronous in Kodi)."""
        self._call(
            "VideoLibrary.Scan",
            {
                "directory": directory,
            },
        )
        logger.info("kodi.sync: action=scan")

    def clean(self) -> None:
        """Clean library: remove entries for files that no longer exist."""
        self._call(
            "VideoLibrary.Clean",
            {
                "content": "musicvideos",
                "showdialogs": False,
            },
        )
        logger.info("kodi.sync: action=clean type=musicvideos")

    def get_music_videos(self) -> dict[str, dict]:
        """Fetch all music videos with artwork: {path: {"id": int, "art": dict}}.

        Paths are stored exactly as Kodi reports them (e.g. SMB URLs).
        """
        result = self._call(
            "VideoLibrary.GetMusicVideos",
            {
                "properties": ["file", "art"],
            },
        )
        mapping: dict[str, dict] = {}
        for mv in result.get("musicvideos", []):
            file_path = mv.get("file", "")
            mv_id = mv.get("musicvideoid")
            if file_path and mv_id is not None:
                mapping[file_path] = {
                    "id": mv_id,
                    "art": mv.get("art", {}),
                }
        logger.debug("kodi.library: count=%d", len(mapping))
        return mapping

    def refresh_music_video(self, musicvideoid: int) -> None:
        """Refresh a single music video (re-reads NFO + clears artwork cache)."""
        self._call(
            "VideoLibrary.RefreshMusicVideo",
            {
                "musicvideoid": musicvideoid,
                "ignorenfo": False,
            },
        )

    def get_textures(self, url: str) -> list[dict]:
        """Find cached textures matching a URL."""
        result = self._call(
            "Textures.GetTextures",
            {
                "properties": ["url"],
                "filter": {
                    "field": "url",
                    "operator": "contains",
                    "value": url,
                },
            },
            quiet=True,
        )
        return result.get("textures", [])

    def remove_texture(self, texture_id: int) -> None:
        """Hard-delete a cached texture (DB record + file on disk)."""
        self._call(
            "Textures.RemoveTexture",
            {
                "textureid": texture_id,
            },
            quiet=True,
        )


def _infer_path_mapping(
    local_paths: list[Path],
    kodi_videos: dict[str, dict],
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

        # Walk backwards, case-insensitive comparison. The two path lists can
        # differ in length (we only compare the common suffix), so strict=False.
        common = 0
        for lp, kp in zip(reversed(local_parts), reversed(kodi_parts), strict=False):
            if lp.lower() == kp.lower():
                common += 1
            else:
                break

        if common < 1:
            continue

        # local prefix = everything before the common suffix
        local_prefix = str(Path(*local_parts[: len(local_parts) - common]))
        kodi_prefix = "/".join(kodi_parts[: len(kodi_parts) - common])

        logger.info(
            "kodi.path_mapping: source=auto local=%s kodi=%s", local_prefix, kodi_prefix
        )
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
    relative = resolved[len(local_prefix) :]
    relative = relative.replace("\\", "/").lstrip("/")
    candidate = f"{kodi_prefix}/{relative}" if relative else kodi_prefix
    # Look up case-insensitive against actual Kodi paths
    return kodi_lookup.get(candidate.lower())


def sync_library(
    client: KodiClient,
    changed_paths: list[Path],
    console: Console,
    quiet: bool = False,
    path_mapping: dict | None = None,
    suppressed: bool = False,
    art_changed_paths: set[Path] | None = None,
    album_poster_folders: set[Path] | None = None,
) -> None:
    """Sync changed files with Kodi: refresh existing, scan for new, clean stale.

    When art_changed_paths is provided, texture cache clearing only runs for
    items in that set (artwork actually changed). Otherwise all items get
    texture clearing as a safe default.

    When album_poster_folders is provided, folder.jpg texture cache entries
    are hard-deleted for those folders.
    """
    if not changed_paths:
        return

    import time

    from festival_organizer.console import (
        StepProgress,
        library_sync_summary_line,
    )

    logger.info("kodi.sync: action=start items=%d", len(changed_paths))
    phase_start = time.perf_counter()

    if not quiet:
        console.print()
        console.rule("Kodi sync", style="dim")

    with StepProgress(console, enabled=not suppressed and not quiet) as sp:
        sp.update("Fetching Kodi library...")
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
                logger.info(
                    "kodi.path_mapping: source=config local=%s kodi=%s",
                    local_prefix,
                    kodi_prefix,
                )

        if not (local_prefix and kodi_prefix):
            inferred = _infer_path_mapping(changed_paths, kodi_videos)
            if inferred:
                local_prefix, kodi_prefix = inferred

        # Build a filename-to-entry index as last-resort fallback (case-insensitive)
        filename_index: dict[str, dict] = {}
        for kodi_path, entry in kodi_videos.items():
            name = kodi_path.rsplit("/", 1)[-1] if "/" in kodi_path else kodi_path
            filename_index[name.lower()] = entry

        # Deduplicate paths (album_poster expansion may add duplicates)
        unique_paths = list(dict.fromkeys(changed_paths))

        refreshed = 0
        not_found = 0
        textures_cleared = 0

        logger.debug("kodi.sync: action=throttle delay_ms=100")

        for i, path in enumerate(unique_paths):
            sp.update(
                f"Refreshing {i + 1}/{len(unique_paths)}",
                filename=path.name,
            )

            entry = None

            # Strategy 1: prefix mapping (case-insensitive)
            if local_prefix and kodi_prefix:
                kodi_path = _translate_path(path, local_prefix, kodi_prefix, kodi_lower)
                if kodi_path:
                    entry = kodi_videos.get(kodi_path)

            # Strategy 2: exact path match (same filesystem)
            if entry is None:
                entry = kodi_videos.get(str(path.resolve()))

            # Strategy 3: filename match (case-insensitive fallback)
            if entry is None:
                entry = filename_index.get(path.name.lower())
                if entry is not None:
                    logger.debug("kodi.match: strategy=filename file=%s", path.name)

            if entry is not None:
                mv_id = entry["id"]

                # Hard-delete texture cache only for items with artwork changes
                needs_texture_clear = (
                    art_changed_paths is None or path in art_changed_paths
                )
                if needs_texture_clear:
                    for art_url in entry.get("art", {}).values():
                        for tex in client.get_textures(art_url):
                            tex_id = tex.get("textureid")
                            if tex_id is not None:
                                client.remove_texture(tex_id)
                                textures_cleared += 1

                client.refresh_music_video(mv_id)
                logger.info("kodi.refresh: file=%s status=ok", path.name)
                refreshed += 1
                time.sleep(0.1)
            else:
                logger.warning(
                    "kodi.refresh: file=%s status=not_found",
                    path.name,
                )
                not_found += 1

        # Clear folder.jpg texture cache for folders with changed album posters
        if album_poster_folders and local_prefix and kodi_prefix:
            for folder in album_poster_folders:
                folder_jpg = folder / "folder.jpg"
                resolved = str(folder_jpg.resolve())
                if resolved.lower().startswith(local_prefix.lower()):
                    relative = (
                        resolved[len(local_prefix) :].replace("\\", "/").lstrip("/")
                    )
                    kodi_folder_path = f"{kodi_prefix}/{relative}"
                    for tex in client.get_textures(kodi_folder_path):
                        tex_id = tex.get("textureid")
                        if tex_id is not None:
                            client.remove_texture(tex_id)
                            textures_cleared += 1

        if textures_cleared:
            logger.info("kodi.texture: action=cleared count=%d", textures_cleared)

        sp.update("Waiting for Kodi to process refreshes...")
        time.sleep(2)

        sp.update("Scanning for new files...")
        client.scan()

        time.sleep(2)

        sp.update("Cleaning stale entries...")
        client.clean()

    elapsed = time.perf_counter() - phase_start

    if not quiet:
        stats: dict[str, int] = {"refreshed": refreshed}
        if textures_cleared:
            stats["textures cleared"] = textures_cleared
        if not_found:
            stats["not yet in library"] = not_found
        console.print(library_sync_summary_line("Kodi", stats, elapsed))
