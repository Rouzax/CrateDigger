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


def test_negative_entry_from_an_older_resolver_is_retried(tmp_path):
    """A cached miss is only as good as the resolver that produced it.

    The punctuation fold and alias matching resolve names that previously
    came back empty, but those names already hold a fresh negative entry.
    Without invalidation the improved lookup would not run for them until
    the 90-day TTL expired.
    """
    raw = {"a-trak": {"mbid": None, "ts": time.time(), "ttl": 90 * 86400}}
    (tmp_path / "mbid_cache.json").write_text(json.dumps(raw))
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    assert not cache.has("A-Trak")


def test_positive_entry_from_an_older_resolver_is_kept(tmp_path):
    """A hit stays valid: better matching cannot improve an MBID we have,
    so there is no reason to re-query thousands of good entries."""
    raw = {"afrojack": {"mbid": "abc-mbid", "ts": time.time(), "ttl": 90 * 86400}}
    (tmp_path / "mbid_cache.json").write_text(json.dumps(raw))
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    assert cache.has("Afrojack")
    assert cache.get("Afrojack") == "abc-mbid"


def test_negative_entry_from_the_current_resolver_is_honoured(tmp_path):
    """Once re-checked by the current resolver, a miss is cached normally."""
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    cache.put("Nobody", None)
    assert cache.has("Nobody")
    assert cache.get("Nobody") is None


def test_legacy_migration_treated_as_expired(tmp_path):
    raw = {"afrojack": "bare-mbid-string"}
    (tmp_path / "mbid_cache.json").write_text(json.dumps(raw))
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    assert not cache.has("Afrojack")


# --- Load logging tests ---


def test_mbid_cache_load_logs_not_found(tmp_path, caplog):
    """New MBID cache logs 'not found' at DEBUG."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="festival_organizer.fanart"):
        MBIDCache(cache_dir=tmp_path / "empty")
    assert any("fanart.mbid_cache: status=not_found" in msg for msg in caplog.messages)


def test_mbid_cache_load_logs_entry_count(tmp_path, caplog):
    """Existing MBID cache logs path and entry count at DEBUG."""
    import logging

    (tmp_path / "mbid_cache.json").write_text(
        json.dumps(
            {
                "tiesto": {"mbid": "abc", "ts": time.time(), "ttl": 86400},
            }
        )
    )
    with caplog.at_level(logging.DEBUG, logger="festival_organizer.fanart"):
        MBIDCache(cache_dir=tmp_path)
    assert any(
        "fanart.mbid_cache: status=loaded" in msg and "entries=1" in msg
        for msg in caplog.messages
    )
