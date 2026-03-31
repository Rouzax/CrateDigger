"""Tests for source cache alias derivation."""
import json
import pytest
from pathlib import Path
from festival_organizer.tracklists.source_cache import SourceCache


@pytest.fixture
def cache_with_sources(tmp_path):
    """Source cache pre-loaded with festival and venue entries."""
    cache_path = tmp_path / "source_cache.json"
    data = {
        "5tb5n3": {"name": "Amsterdam Music Festival", "slug": "amsterdam-music-festival", "type": "Open Air / Festival", "country": "Netherlands"},
        "u8bf5c": {"name": "Ultra Music Festival Miami", "slug": "ultra-music-festival-miami", "type": "Open Air / Festival", "country": "United States"},
        "hdfr2c": {"name": "Johan Cruijff ArenA", "slug": "johan-cruijff-arena-amsterdam", "type": "Event Location", "country": "Netherlands"},
        "f4lzj3": {"name": "Amsterdam Dance Event", "slug": "amsterdam-dance-event", "type": "Conference", "country": "Netherlands"},
        "m3b0d3": {"name": "A State Of Trance", "slug": "a-state-of-trance", "type": "Radio Channel", "country": ""},
        "fgcfkm": {"name": "Tomorrowland", "slug": "tomorrowland", "type": "Open Air / Festival", "country": "Belgium"},
    }
    cache_path.write_text(json.dumps(data))
    return SourceCache(cache_path=cache_path)


def test_derive_aliases_festivals(cache_with_sources):
    aliases = cache_with_sources.derive_aliases()
    assert aliases["amf"] == "Amsterdam Music Festival"
    assert aliases["umfm"] == "Ultra Music Festival Miami"


def test_derive_aliases_includes_conferences(cache_with_sources):
    aliases = cache_with_sources.derive_aliases()
    assert aliases["ade"] == "Amsterdam Dance Event"


def test_derive_aliases_excludes_venues(cache_with_sources):
    """Event Location (venues) should not produce aliases."""
    aliases = cache_with_sources.derive_aliases()
    assert "jca" not in aliases  # Johan Cruijff ArenA


def test_derive_aliases_excludes_radio(cache_with_sources):
    aliases = cache_with_sources.derive_aliases()
    assert "asot" not in aliases  # A State Of Trance — radio, not festival


def test_derive_aliases_skips_single_word(cache_with_sources):
    """Single-word festival names don't produce abbreviations."""
    aliases = cache_with_sources.derive_aliases()
    assert "t" not in aliases  # Tomorrowland has no multi-word abbreviation


def test_derive_aliases_empty_cache(tmp_path):
    cache_path = tmp_path / "source_cache.json"
    cache = SourceCache(cache_path=cache_path)
    assert cache.derive_aliases() == {}
