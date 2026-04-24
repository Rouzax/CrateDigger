import json
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


def test_promote_concert_to_festival(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "sc.json")
    cache.put("rch80m", {"name": "A State Of Trance Festival", "slug": "asot", "type": "Concert / Live Event", "country": "Netherlands"})
    cache.put("tslp1m", {"name": "Ahoy Rotterdam", "slug": "ahoy", "type": "Event Location", "country": "Netherlands"})
    groups = cache.group_by_type(["rch80m", "tslp1m"])
    assert "Open Air / Festival" in groups
    assert "A State Of Trance Festival" in groups["Open Air / Festival"]
    assert "Concert / Live Event" not in groups


def test_promote_event_promoter_to_festival(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "sc.json")
    cache.put("5j4wgtv", {"name": "We Belong Here", "slug": "wbh", "type": "Event Promoter", "country": "United States"})
    cache.put("7xp1dkc", {"name": "Historic Virginia Key Park", "slug": "hvkp", "type": "Event Location", "country": "United States"})
    groups = cache.group_by_type(["5j4wgtv", "7xp1dkc"])
    assert "Open Air / Festival" in groups
    assert "We Belong Here" in groups["Open Air / Festival"]
    assert "Event Promoter" not in groups


def test_no_promotion_when_festival_exists(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "sc.json")
    cache.put("u8bf5c", {"name": "Ultra Music Festival Miami", "slug": "umf", "type": "Open Air / Festival", "country": "United States"})
    cache.put("v088zc", {"name": "Resistance", "slug": "resistance", "type": "Event Promoter", "country": "Worldwide"})
    groups = cache.group_by_type(["u8bf5c", "v088zc"])
    assert groups["Open Air / Festival"] == ["Ultra Music Festival Miami"]
    assert "Event Promoter" in groups
    assert "Resistance" in groups["Event Promoter"]


def test_concert_promoted_before_event_promoter(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "sc.json")
    cache.put("aaa", {"name": "Some Concert", "slug": "sc", "type": "Concert / Live Event", "country": "NL"})
    cache.put("bbb", {"name": "Some Promoter", "slug": "sp", "type": "Event Promoter", "country": "NL"})
    groups = cache.group_by_type(["aaa", "bbb"])
    assert groups["Open Air / Festival"] == ["Some Concert"]
    assert "Concert / Live Event" not in groups


def test_cache_expired_entry_is_miss(tmp_path):
    """Expired entry should return None on get()."""
    cache = SourceCache(cache_path=tmp_path / "sc.json", ttl_days=0)
    cache.put("abc", {"name": "TML", "slug": "tml", "type": "Open Air / Festival", "country": "Belgium"})
    assert cache.get("abc") is None


def test_cache_old_entries_without_ts_expire(tmp_path):
    """Entries without ts field (from old cache) should be treated as expired."""
    path = tmp_path / "sc.json"
    path.write_text(json.dumps({"abc": {"name": "TML", "slug": "tml", "type": "Open Air / Festival", "country": "Belgium"}}))
    cache = SourceCache(cache_path=path, ttl_days=90)
    assert cache.get("abc") is None


# --- Load logging tests ---


def test_cache_load_logs_not_found(tmp_path, caplog):
    """New cache file logs 'not found' at DEBUG."""
    import logging
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.source_cache"):
        SourceCache(cache_path=tmp_path / "source_cache.json")
    assert any("not found" in msg for msg in caplog.messages)


def test_cache_load_logs_entry_count(tmp_path, caplog):
    """Existing cache file logs path and entry count at DEBUG."""
    import logging
    path = tmp_path / "source_cache.json"
    c = SourceCache(cache_path=path)
    c.put("x", {"name": "X", "slug": "x", "type": "Club", "country": "US"})
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.tracklists.source_cache"):
        SourceCache(cache_path=path)
    assert any("Loaded source cache from" in msg and "1 entr" in msg for msg in caplog.messages)
