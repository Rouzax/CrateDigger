"""Shared test configuration for CrateDigger tests."""
import json
from pathlib import Path

import pytest

from festival_organizer import paths as _paths_module
from festival_organizer.config import DEFAULT_CONFIG
from festival_organizer.models import MediaFile


def make_mediafile(*, place: str | None = None, place_kind: str | None = None, **kwargs) -> MediaFile:
    """Construct a MediaFile and auto-populate ``place`` / ``place_kind`` for tests.

    Production code populates ``mf.place`` and ``mf.place_kind`` in
    ``analyzer.py`` via ``Config.resolve_place_for_media(mf)`` after MediaFile
    construction. Tests that bypass the analyzer use this helper to mimic that
    auto-population so the templates engine (which routes via ``mf.place``) sees
    a non-empty value.

    The chain mirrors ``Config.resolve_place_for_media``:
    festival -> venue -> location -> artist. Pass ``place=`` and/or
    ``place_kind=`` explicitly to override.
    """
    mf = MediaFile(**kwargs)
    if place is not None:
        mf.place = place
    elif mf.festival.strip():
        mf.place = mf.festival.strip()
        mf.place_kind = "festival"
    elif mf.venue.strip():
        mf.place = mf.venue.strip()
        mf.place_kind = "venue"
    elif mf.location.strip():
        mf.place = mf.location.strip()
        mf.place_kind = "location"
    elif mf.artist.strip():
        mf.place = mf.artist.strip()
        mf.place_kind = "artist"
    if place_kind is not None:
        mf.place_kind = place_kind
    return mf


@pytest.fixture(autouse=True)
def _reset_per_process_state():
    """Reset module-level once-per-process flags between tests.

    ``paths._migrated_this_process`` gates the legacy-path auto-migration so
    it runs at most once per process. Reset so each test that constructs a
    Config sees a fresh migration attempt.
    """
    _paths_module._migrated_this_process = False
    yield
    _paths_module._migrated_this_process = False

_REPO_ROOT = Path(__file__).resolve().parent.parent

_artists = json.loads((_REPO_ROOT / "artists.example.json").read_text(encoding="utf-8"))
_places = json.loads((_REPO_ROOT / "places.example.json").read_text(encoding="utf-8"))

# Build alias and config dicts from the unified place registry format
_place_aliases: dict[str, list[str]] = {}
_place_config: dict[str, dict] = {}
for _canon, _pc in _places.items():
    if _canon.startswith("_") or not isinstance(_pc, dict):
        continue
    _aliases = list(_pc.get("aliases", []))
    for _ed_conf in _pc.get("editions", {}).values():
        _aliases.extend(_ed_conf.get("aliases", []))
    _place_aliases[_canon] = _aliases
    _place_config[_canon] = _pc

# Config dict that includes everything tests need. Uses the example JSON
# files as the single source of truth for aliases, groups, and place config.
TEST_CONFIG = {
    **DEFAULT_CONFIG,
    "place_aliases": _place_aliases,
    "place_config": _place_config,
    "artist_aliases": _artists["aliases"],
    "artist_groups": _artists["groups"],
}
