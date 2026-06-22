"""Local cache for 1001Tracklists DJ profile metadata (aliases, groups, artwork).

Logging:
    Logger: 'festival_organizer.tracklists.dj_cache'
    Key events:
        - dj_cache.load (DEBUG): DJ cache loaded from path with entry count
        - dj_cache.load_failed (DEBUG): Could not read or parse DJ cache file
        - dj_cache.not_found (DEBUG): DJ cache file does not exist yet
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
    name, artwork_url, aliases, member_of groups, and group members.
    Persists under `paths.cache_dir()` (see `festival_organizer.paths`).
    """

    def __init__(self, cache_path: Path | None = None, ttl_days: int = 90):
        self._path = (
            cache_path
            if cache_path is not None
            else paths.cache_dir() / "dj_cache.json"
        )
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                logger.debug(
                    "dj_cache.load: path=%s entries=%d", self._path, len(self._data)
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.debug('dj_cache.load_failed: error="%s"', e)
                self._data = {}
        else:
            logger.debug("dj_cache.not_found: path=%s", self._path)

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

    def slugs(self) -> set[str]:
        """All cached slugs (dict keys), regardless of freshness."""
        return set(self._data.keys())

    def all_artwork_urls(self) -> dict[str, str]:
        """Map slug -> artwork_url for every cached entry that has one.

        Freshness-agnostic (same source set as :meth:`slugs`): the stored URL is
        the best available, and identify refreshes each entry on its own TTL.
        Used to warm the per-artist image cache directly from the DJ cache.
        """
        return {
            slug: entry["artwork_url"]
            for slug, entry in self._data.items()
            if entry.get("artwork_url")
        }

    def derive_entry_names(self) -> set[str]:
        """Lowercased canonical names of every cached entry.

        A single /dj/ entry means 1001TL treats the name as one act, so these
        names form the 'do not split' guard (e.g. 'above & beyond').
        """
        from festival_organizer.normalization import fix_mojibake

        names: set[str] = set()
        for entry in self._data.values():
            name = entry.get("name", "")
            if name:
                names.add(fix_mojibake(name).lower())
        return names

    def slug_for_name(self, name: str) -> str | None:
        """Resolve a display name (or alias) to its cached slug, or None.

        Matches on slugify() so diacritics, case, trailing dots and '&' spelling
        do not matter ('Tiesto'/'Tiësto', 'Fred again'/'Fred again..').
        """
        from festival_organizer.normalization import slugify

        if not name:
            return None
        index = self._name_index()
        return index.get(slugify(name))

    def _name_index(self) -> dict[str, str]:
        from festival_organizer.normalization import slugify

        index: dict[str, str] = {}
        for slug, entry in self._data.items():
            entry_name = entry.get("name", "")
            if entry_name:
                index.setdefault(slugify(entry_name), slug)
            for alias in entry.get("aliases", []):
                alias_name = alias.get("name", "")
                if alias_name:
                    index.setdefault(slugify(alias_name), slug)
        return index

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
        """Map group SLUG -> [member name, ...], complete lineup.

        Combines each group entry's directly captured "Group Members"
        (`members`) with the reverse-derivation of every cached DJ's
        `member_of`. Directly-stored members complete lineups whose
        individual members are not themselves cached (e.g. Above & Beyond).
        Keyed by slug so callers can look up via the file's album-artist slugs.
        """
        groups: dict[str, list[str]] = {}
        # (a) directly captured members on each group entry
        for slug, entry in self._data.items():
            for member in entry.get("members", []):
                name = member.get("name", "")
                if name:
                    groups.setdefault(slug, []).append(name)
        # (b) reverse-derive from member_of for groups without a captured list
        name_to_slug = {e.get("name", ""): s for s, e in self._data.items()}
        for entry in self._data.values():
            member_name = entry.get("name", "")
            if not member_name:
                continue
            for group in entry.get("member_of", []):
                group_name = group.get("name", "")
                group_slug = group.get("slug", "") or name_to_slug.get(group_name, "")
                if group_slug and member_name not in groups.get(group_slug, []):
                    groups.setdefault(group_slug, []).append(member_name)
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
                logger.warning(
                    'dj_cache.fetch: status=failed slug=%s error="%s"', slug, exc
                )
                continue
            if entry is None:
                logger.warning("dj_cache.fetch: status=empty slug=%s", slug)
                continue
            self.put(slug, entry)
            resolved[slug] = entry
            if progress is not None:
                progress(slug, i, len(misses))
        return resolved

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
