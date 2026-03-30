"""Local cache for 1001Tracklists /source/ page metadata (type, country)."""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path.home() / ".cratedigger" / "source_cache.json"

# Maps 1001TL source types to MKV tag names.
SOURCE_TYPE_TO_TAG: dict[str, str] = {
    "Open Air / Festival": "CRATEDIGGER_1001TL_FESTIVAL",
    "Event Location": "CRATEDIGGER_1001TL_VENUE",
    "Conference": "CRATEDIGGER_1001TL_CONFERENCE",
    "Radio Channel": "CRATEDIGGER_1001TL_RADIO",
}


class SourceCache:
    """Read-through cache for 1001TL source page metadata.

    Keyed by source ID (e.g. "5tb5n3"). Each entry stores name, slug, type, country.
    Persists to ~/.cratedigger/source_cache.json.
    """

    def __init__(self, cache_path: Path | None = None):
        self._path = cache_path or DEFAULT_PATH
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
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get(self, source_id: str) -> dict | None:
        return self._data.get(source_id)

    def put(self, source_id: str, entry: dict) -> None:
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
        return groups
