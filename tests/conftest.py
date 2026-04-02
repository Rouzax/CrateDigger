"""Shared test configuration for CrateDigger tests."""
import json
from pathlib import Path

from festival_organizer.config import DEFAULT_CONFIG

_REPO_ROOT = Path(__file__).resolve().parent.parent

_artists = json.loads((_REPO_ROOT / "artists.example.json").read_text(encoding="utf-8"))
_festivals = json.loads((_REPO_ROOT / "festivals.example.json").read_text(encoding="utf-8"))

# Build alias and config dicts from unified festival format
_fest_aliases: dict[str, list[str]] = {}
_fest_config: dict[str, dict] = {}
for _canon, _fc in _festivals.items():
    if _canon.startswith("_") or not isinstance(_fc, dict):
        continue
    _aliases = list(_fc.get("aliases", []))
    for _ed_conf in _fc.get("editions", {}).values():
        _aliases.extend(_ed_conf.get("aliases", []))
    _fest_aliases[_canon] = _aliases
    _fest_config[_canon] = _fc

# Config dict that includes everything tests need. Uses the example JSON
# files as the single source of truth for aliases, groups, and festival config.
TEST_CONFIG = {
    **DEFAULT_CONFIG,
    "festival_aliases": _fest_aliases,
    "festival_config": _fest_config,
    "artist_aliases": _artists["aliases"],
    "artist_groups": _artists["groups"],
}
