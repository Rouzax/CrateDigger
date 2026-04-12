import json
import time

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
