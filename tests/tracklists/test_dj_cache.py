"""Tests for DjCache TTL behaviour."""
import json
import time
from unittest.mock import patch

from festival_organizer.tracklists.dj_cache import DjCache


def test_put_stamps_ttl_field(tmp_path):
    cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    cache.put("tiesto", {"name": "Tiesto"})
    raw = json.loads((tmp_path / "dj_cache.json").read_text())
    assert "ttl" in raw["tiesto"]
    assert 90 * 86400 * 0.8 <= raw["tiesto"]["ttl"] <= 90 * 86400 * 1.2


def test_get_honours_per_entry_ttl(tmp_path):
    cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    raw = {"tiesto": {"name": "Tiesto", "ts": time.time() - 200, "ttl": 100.0}}
    (tmp_path / "dj_cache.json").write_text(json.dumps(raw))
    cache._load()
    assert cache.get("tiesto") is None


def test_get_legacy_entry_uses_class_default(tmp_path):
    raw = {"tiesto": {"name": "Tiesto", "ts": time.time() - 10}}
    (tmp_path / "dj_cache.json").write_text(json.dumps(raw))
    cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    assert cache.get("tiesto") is not None


def test_default_ttl_is_90_days_explicit():
    cache = DjCache(cache_path=None, ttl_days=90)
    assert cache._ttl_seconds == 90 * 86400


def test_default_ttl_signature_is_90_days(tmp_path):
    cache = DjCache(cache_path=tmp_path / "dj_cache.json")
    assert cache._ttl_seconds == 90 * 86400


def test_canonical_name_resolves(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})
    assert cache.canonical_name("afrojack") == "Afrojack"


def test_canonical_name_falls_back_to_slug(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    assert cache.canonical_name("unknown") == "unknown"


def test_canonical_name_fallback_value(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    assert cache.canonical_name("unknown", fallback="X") == "X"


def test_dj_cache_uses_cache_dir(tmp_path):
    with patch("festival_organizer.tracklists.dj_cache.paths") as mock_paths:
        mock_paths.cache_dir.return_value = tmp_path
        mock_paths.ensure_parent.side_effect = lambda p: (
            p.parent.mkdir(parents=True, exist_ok=True),
            p,
        )[1]
        cache = DjCache()
        cache.put("tiesto", {"name": "Tiesto"})
    assert (tmp_path / "dj_cache.json").is_file()


def test_canonical_name_heals_mojibake_on_read(tmp_path):
    """Legacy cache entries with mojibake bytes self-heal via fix_mojibake."""
    import json
    import time
    raw = {"tiesto": {"name": "Ti\u251c\u00bdsto", "ts": time.time()}}  # "Ti├½sto"
    (tmp_path / "c.json").write_text(json.dumps(raw))
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    # ftfy-based fix_mojibake should repair the mojibake
    # (some mojibake patterns may not be recoverable; this one comes from
    # UTF-8 bytes decoded as cp437, which ftfy handles well).
    result = cache.canonical_name("tiesto")
    # Either fully healed to "Tiësto" or at least not the raw mojibake
    assert "├" not in result, f"raw mojibake leaked through: {result!r}"
