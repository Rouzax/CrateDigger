import json
import time
from unittest.mock import patch

from festival_organizer.tracklists.source_cache import SourceCache


def test_put_stamps_ttl_field(tmp_path):
    cache = SourceCache(cache_path=tmp_path / "source_cache.json", ttl_days=365)
    cache.put("abc123", {"name": "EDC Las Vegas", "type": "Open Air / Festival"})
    raw = json.loads((tmp_path / "source_cache.json").read_text())
    assert "ttl" in raw["abc123"]
    assert 365 * 86400 * 0.8 <= raw["abc123"]["ttl"] <= 365 * 86400 * 1.2


def test_get_honours_per_entry_ttl(tmp_path):
    raw = {"abc": {"name": "x", "type": "y", "ts": time.time() - 200, "ttl": 100.0}}
    (tmp_path / "source_cache.json").write_text(json.dumps(raw))
    cache = SourceCache(cache_path=tmp_path / "source_cache.json", ttl_days=365)
    assert cache.get("abc") is None


def test_get_legacy_entry_uses_class_default(tmp_path):
    raw = {"abc": {"name": "x", "type": "y", "ts": time.time() - 10}}
    (tmp_path / "source_cache.json").write_text(json.dumps(raw))
    cache = SourceCache(cache_path=tmp_path / "source_cache.json", ttl_days=365)
    assert cache.get("abc") is not None


def test_default_ttl_is_365_days():
    cache = SourceCache(cache_path=None)
    assert cache._ttl_seconds == 365 * 86400


def test_club_source_type_maps_to_venue_tag():
    """1001TL uses 'Club' for named physical venues like Alexandra Palace
    London. It must route to CRATEDIGGER_1001TL_VENUE so the venue surfaces
    on the file, not fall through silently."""
    from festival_organizer.tracklists.source_cache import SOURCE_TYPE_TO_TAG
    assert SOURCE_TYPE_TO_TAG["Club"] == "CRATEDIGGER_1001TL_VENUE"


def test_source_cache_uses_cache_dir(tmp_path):
    with patch("festival_organizer.tracklists.source_cache.paths") as mock_paths:
        mock_paths.cache_dir.return_value = tmp_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        cache = SourceCache()
        cache.put("abc123", {"name": "EDC Las Vegas", "type": "Open Air / Festival"})
    assert (tmp_path / "source_cache.json").is_file()


def test_club_group_by_type_is_not_promoted_to_festival(tmp_path):
    """A Club must remain a Club in the grouped output, never be promoted
    to 'Open Air / Festival' by the fallback logic."""
    cache = SourceCache(cache_path=tmp_path / "source_cache.json", ttl_days=365)
    cache.put("5fg8dv", {"name": "Alexandra Palace London", "slug": "alexandra-palace-london", "type": "Club"})
    groups = cache.group_by_type(["5fg8dv"])
    assert groups == {"Club": ["Alexandra Palace London"]}
    assert "Open Air / Festival" not in groups
