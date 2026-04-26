"""Shared test configuration for CrateDigger tests."""
import json
from pathlib import Path

import pytest

from festival_organizer import config as _config_module
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
    elif mf.festival:
        mf.place = mf.festival
        mf.place_kind = "festival"
    elif mf.venue:
        mf.place = mf.venue
        mf.place_kind = "venue"
    elif mf.location:
        mf.place = mf.location
        mf.place_kind = "location"
    elif mf.artist:
        mf.place = mf.artist
        mf.place_kind = "artist"
    if place_kind is not None:
        mf.place_kind = place_kind
    return mf


@pytest.fixture(autouse=True)
def _reset_deprecation_log_state():
    """Clear the per-process deprecation-log dedup set so tests don't suppress each other's logs."""
    _config_module._emitted_deprecations.clear()
    yield
    _config_module._emitted_deprecations.clear()

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
