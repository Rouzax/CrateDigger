import json
from pathlib import Path
from festival_organizer.tracklists.source_cache import SourceCache


def test_cache_miss_returns_none(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    assert cache.get("nonexistent") is None


def test_cache_put_and_get(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    cache.put("abc123", {"name": "Tomorrowland", "slug": "tomorrowland",
                         "type": "Open Air / Festival", "country": "Belgium"})
    entry = cache.get("abc123")
    assert entry["name"] == "Tomorrowland"
    assert entry["type"] == "Open Air / Festival"
    assert entry["country"] == "Belgium"


def test_cache_persists_to_disk(tmp_path):
    path = tmp_path / "source_cache.json"
    cache1 = SourceCache(cache_path=path)
    cache1.put("abc123", {"name": "TML", "slug": "tml", "type": "Open Air / Festival", "country": "Belgium"})
    cache2 = SourceCache(cache_path=path)
    assert cache2.get("abc123")["name"] == "TML"


def test_cache_file_auto_created(tmp_path):
    path = tmp_path / "sub" / "source_cache.json"
    cache = SourceCache(cache_path=path)
    cache.put("x", {"name": "X", "slug": "x", "type": "Club", "country": "US"})
    assert path.exists()
    data = json.loads(path.read_text())
    assert "x" in data


def test_find_by_type(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    cache.put("a", {"name": "AMF", "slug": "amf", "type": "Open Air / Festival", "country": "Netherlands"})
    cache.put("b", {"name": "Johan Cruijff ArenA Amsterdam", "slug": "johan-cruijff-arena-amsterdam", "type": "Event Location", "country": "Netherlands"})
    cache.put("c", {"name": "ADE", "slug": "ade", "type": "Conference", "country": "Netherlands"})
    venues = cache.find_by_type(["a", "b", "c"], "Event Location")
    assert len(venues) == 1
    assert venues[0]["name"] == "Johan Cruijff ArenA Amsterdam"


def test_group_by_type(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json")
    cache.put("a", {"name": "AMF", "slug": "amf", "type": "Open Air / Festival", "country": "Netherlands"})
    cache.put("b", {"name": "Johan Cruijff ArenA Amsterdam", "slug": "johan-cruijff-arena-amsterdam", "type": "Event Location", "country": "Netherlands"})
    cache.put("c", {"name": "ADE", "slug": "ade", "type": "Conference", "country": "Netherlands"})
    grouped = cache.group_by_type(["a", "b", "c"])
    assert grouped["Open Air / Festival"] == ["AMF"]
    assert grouped["Event Location"] == ["Johan Cruijff ArenA Amsterdam"]
    assert grouped["Conference"] == ["ADE"]
