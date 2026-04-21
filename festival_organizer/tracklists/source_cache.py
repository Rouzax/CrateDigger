"""Local cache for 1001Tracklists /source/ page metadata (type, country).

Logging:
    Logger: 'festival_organizer.tracklists.source_cache'
    Key events:
        - cache.load_failed (DEBUG): Could not read or parse source cache file
    See docs/logging.md for full guidelines.
"""
import json
import logging
import time
from pathlib import Path

from festival_organizer import paths
from festival_organizer.cache_ttl import is_fresh, jittered_ttl_seconds

logger = logging.getLogger(__name__)

# Maps 1001TL source types to MKV tag names. Club is treated as a venue,
# since 1001TL uses it for physical venues like Alexandra Palace London that
# are not categorized as "Event Location".
SOURCE_TYPE_TO_TAG: dict[str, str] = {
    "Open Air / Festival": "CRATEDIGGER_1001TL_FESTIVAL",
    "Event Location": "CRATEDIGGER_1001TL_VENUE",
    "Club": "CRATEDIGGER_1001TL_VENUE",
    "Conference": "CRATEDIGGER_1001TL_CONFERENCE",
    "Radio Channel": "CRATEDIGGER_1001TL_RADIO",
}


class SourceCache:
    """Read-through cache for 1001TL source page metadata.

    Keyed by source ID (e.g. "5tb5n3"). Each entry stores name, slug, type, country.
    Persists under `paths.cache_dir()` (see `festival_organizer.paths`).
    """

    def __init__(self, cache_path: Path | None = None, ttl_days: int = 365):
        self._path = cache_path if cache_path is not None else paths.cache_dir() / "source_cache.json"
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug("Could not load source cache: %s", e)
                self._data = {}

    def _save(self) -> None:
        paths.ensure_parent(self._path)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _is_fresh(self, entry: dict) -> bool:
        return is_fresh(entry, self._ttl_seconds)

    def get(self, source_id: str) -> dict | None:
        entry = self._data.get(source_id)
        if entry is None or not self._is_fresh(entry):
            return None
        return entry

    def put(self, source_id: str, entry: dict) -> None:
        entry["ts"] = time.time()
        entry["ttl"] = jittered_ttl_seconds(self._ttl_days)
        self._data[source_id] = entry
        self._save()

    def find_by_type(self, source_ids: list[str], source_type: str) -> list[dict]:
        """Return cached entries matching the given type from a list of source IDs."""
        return [
            self._data[sid]
            for sid in source_ids
            if sid in self._data and self._data[sid].get("type") == source_type
        ]

    def group_by_type(self, source_ids: list[str]) -> dict[str, list[str]]:
        """Group source names by their type. Returns {type: [name, ...]}."""
        groups: dict[str, list[str]] = {}
        for sid in source_ids:
            entry = self._data.get(sid)
            if entry:
                groups.setdefault(entry["type"], []).append(entry["name"])
        # Promote unmapped types to festival when no festival exists
        if "Open Air / Festival" not in groups:
            for fallback_type in ("Concert / Live Event", "Event Promoter"):
                if fallback_type in groups:
                    groups["Open Air / Festival"] = groups.pop(fallback_type)
                    break
        return groups

    def all_names_lower(self) -> set[str]:
        """Return lowercased set of all cached source names."""
        return {entry["name"].lower() for entry in self._data.values() if entry.get("name")}
