import json
import time

from festival_organizer.fanart import MBIDCache


def test_put_stamps_ttl_field(tmp_path):
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    cache.put("Afrojack", "abc-mbid")
    raw = json.loads((tmp_path / "mbid_cache.json").read_text())
    assert "ttl" in raw["afrojack"]
    assert 90 * 86400 * 0.8 <= raw["afrojack"]["ttl"] <= 90 * 86400 * 1.2


def test_get_honours_per_entry_ttl(tmp_path):
    raw = {"afrojack": {"mbid": "x", "ts": time.time() - 200, "ttl": 100.0}}
    (tmp_path / "mbid_cache.json").write_text(json.dumps(raw))
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    assert not cache.has("Afrojack")


def test_legacy_migration_treated_as_expired(tmp_path):
    raw = {"afrojack": "bare-mbid-string"}
    (tmp_path / "mbid_cache.json").write_text(json.dumps(raw))
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    assert not cache.has("Afrojack")
