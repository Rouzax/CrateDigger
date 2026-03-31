"""Shared test configuration for CrateDigger tests."""
import json
from pathlib import Path

from festival_organizer.config import DEFAULT_CONFIG

_REPO_ROOT = Path(__file__).resolve().parent.parent

_artists = json.loads((_REPO_ROOT / "artists.example.json").read_text(encoding="utf-8"))
_festivals = json.loads((_REPO_ROOT / "festivals.example.json").read_text(encoding="utf-8"))

# Config dict that includes everything tests need. Uses the example JSON
# files as the single source of truth for aliases, groups, and festival config.
TEST_CONFIG = {
    **DEFAULT_CONFIG,
    "festival_aliases": _festivals["aliases"],
    "festival_config": _festivals["config"],
    "artist_aliases": _artists["aliases"],
    "artist_groups": _artists["groups"],
}
