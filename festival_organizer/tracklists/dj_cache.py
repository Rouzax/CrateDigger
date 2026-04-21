"""Local cache for 1001Tracklists DJ profile metadata (aliases, groups, artwork).

Logging:
    Logger: 'festival_organizer.tracklists.dj_cache'
    Key events:
        - cache.load_failed (DEBUG): Could not read or parse DJ cache file
    See docs/logging.md for full guidelines.
"""
import json
import logging
import time
from pathlib import Path

from festival_organizer import paths
from festival_organizer.cache_ttl import is_fresh, jittered_ttl_seconds

logger = logging.getLogger(__name__)


class DjCache:
    """Read-through cache for 1001TL DJ profile data with TTL-based expiry.

    Keyed by DJ slug (e.g. "tiesto", "arminvanbuuren"). Each entry stores
    name, artwork_url, aliases, and member_of groups.
    Persists under `paths.cache_dir()` (see `festival_organizer.paths`).
    """

    def __init__(self, cache_path: Path | None = None, ttl_days: int = 90):
        self._path = cache_path if cache_path is not None else paths.cache_dir() / "dj_cache.json"
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Could not load DJ cache: %s", e)
                self._data = {}

    def _save(self) -> None:
        paths.ensure_parent(self._path)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _is_fresh(self, entry: dict) -> bool:
        return is_fresh(entry, self._ttl_seconds)

    def get(self, slug: str) -> dict | None:
        entry = self._data.get(slug)
        if entry is None or not self._is_fresh(entry):
            return None
        return entry

    def put(self, slug: str, entry: dict) -> None:
        entry["ts"] = time.time()
        entry["ttl"] = jittered_ttl_seconds(self._ttl_days)
        self._data[slug] = entry
        self._save()

    def derive_artist_aliases(self) -> dict[str, str]:
        """Build alias_name -> canonical_name map from all cached DJ profiles.

        For example, if Tiesto has aliases VER:WEST and Allure, returns
        {"VER:WEST": "Tiesto", "Allure": "Tiesto"}.
        """
        aliases: dict[str, str] = {}
        for entry in self._data.values():
            canonical = entry.get("name", "")
            for alias in entry.get("aliases", []):
                alias_name = alias.get("name", "")
                if alias_name:
                    aliases[alias_name] = canonical
        return aliases

    def derive_artist_groups(self) -> set[str]:
        """Collect lowercased group names from all cached member_of entries.

        Returns e.g. {"gaia", "logica"}.
        """
        groups: set[str] = set()
        for entry in self._data.values():
            for group in entry.get("member_of", []):
                name = group.get("name", "")
                if name:
                    groups.add(name.lower())
        return groups

    def derive_group_members(self) -> dict[str, list[str]]:
        """Build group_name -> [member_name, ...] mapping from all cached DJ profiles.

        Scans all cached DJs and reverses their member_of entries.
        For example, if Armin van Buuren has member_of: [{name: "Gaia"}],
        returns {"Gaia": ["Armin van Buuren"]}.
        """
        groups: dict[str, list[str]] = {}
        for entry in self._data.values():
            member_name = entry.get("name", "")
            if not member_name:
                continue
            for group in entry.get("member_of", []):
                group_name = group.get("name", "")
                if group_name:
                    groups.setdefault(group_name, []).append(member_name)
        return groups

    def get_or_fetch_many(
        self,
        slugs,
        fetcher,
        progress=None,
    ) -> dict[str, dict]:
        """Resolve a batch of slugs, fetching any not in cache via fetcher(slug).

        Parameters
        ----------
        slugs : iterable of str
            Slugs to resolve. Duplicates are deduped.
        fetcher : callable[str, dict | None]
            Called for every slug not present in the cache. Returns a profile
            dict (will be put into the cache) or None (skipped with a
            WARNING-level log). The caller is responsible for rate limiting
            and I/O; this helper just loops.
        progress : optional callable[str, int, int]
            Called as progress(slug, done_count, total_misses) after each
            successful fetch so callers can drive a Rich progress display.

        Returns
        -------
        dict[str, dict]
            Resolved entries keyed by slug. Slugs that failed to fetch are
            omitted.
        """
        unique = list(dict.fromkeys(slugs))
        resolved: dict[str, dict] = {}
        misses: list[str] = []
        for slug in unique:
            hit = self.get(slug)
            if hit is not None:
                resolved[slug] = hit
            else:
                misses.append(slug)

        for i, slug in enumerate(misses, start=1):
            try:
                entry = fetcher(slug)
            except Exception as exc:
                logger.warning("Artist fetch failed for slug '%s': %s", slug, exc)
                continue
            if entry is None:
                logger.warning("Artist fetch returned no data for slug '%s'", slug)
                continue
            self.put(slug, entry)
            resolved[slug] = entry
            if progress is not None:
                progress(slug, i, len(misses))
        return resolved

    def all_names_lower(self) -> set[str]:
        """Return lowercased set of all cached DJ canonical names."""
        return {entry["name"].lower() for entry in self._data.values() if entry.get("name")}

    def canonical_name(self, slug: str, fallback: str | None = None) -> str:
        """Return the canonical name for a slug, or fallback/slug when unknown.

        Applies mojibake normalisation on read so cache entries written by an
        earlier buggy version (with Latin-1-decoded UTF-8 bytes like "Ti├½sto"
        or "KÃ¶lsch") self-heal the first time they are read back.
        """
        from festival_organizer.normalization import fix_mojibake
        entry = self._data.get(slug)
        if entry and entry.get("name"):
            return fix_mojibake(entry["name"])
        return fallback if fallback is not None else slug
