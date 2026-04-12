"""Tests for the shared cache TTL helper."""
import time
from festival_organizer.cache_ttl import jittered_ttl_seconds, is_fresh
from festival_organizer.cache_ttl import hashed_jitter_factor


def test_jittered_ttl_within_bounds():
    base_days = 90
    base_seconds = base_days * 86400
    lo = base_seconds * 0.8
    hi = base_seconds * 1.2
    samples = [jittered_ttl_seconds(base_days) for _ in range(1000)]
    assert all(lo <= s <= hi for s in samples)


def test_jittered_ttl_has_variance():
    samples = {jittered_ttl_seconds(90) for _ in range(100)}
    assert len(samples) > 50  # not a constant


def test_jittered_ttl_custom_jitter():
    base_seconds = 10 * 86400
    samples = [jittered_ttl_seconds(10, jitter_pct=0.5) for _ in range(200)]
    assert all(base_seconds * 0.5 <= s <= base_seconds * 1.5 for s in samples)


def test_is_fresh_uses_entry_ttl_when_present():
    entry = {"ts": time.time() - 100, "ttl": 200.0}
    assert is_fresh(entry, default_ttl_seconds=50.0) is True


def test_is_fresh_falls_back_to_default_for_legacy_entry():
    entry = {"ts": time.time() - 100}
    assert is_fresh(entry, default_ttl_seconds=200.0) is True
    assert is_fresh(entry, default_ttl_seconds=50.0) is False


def test_is_fresh_expired():
    entry = {"ts": time.time() - 500, "ttl": 100.0}
    assert is_fresh(entry, default_ttl_seconds=1000.0) is False


def test_is_fresh_missing_ts():
    assert is_fresh({}, default_ttl_seconds=1000.0) is False


def test_hashed_jitter_factor_deterministic():
    assert hashed_jitter_factor("abc") == hashed_jitter_factor("abc")


def test_hashed_jitter_factor_bounds():
    samples = [hashed_jitter_factor(f"key-{i}") for i in range(500)]
    assert all(0.8 <= s <= 1.2 for s in samples)


def test_hashed_jitter_factor_has_variance():
    samples = {round(hashed_jitter_factor(f"key-{i}"), 3) for i in range(500)}
    assert len(samples) > 100


def test_hashed_jitter_factor_custom_jitter():
    samples = [hashed_jitter_factor(f"k{i}", jitter_pct=0.5) for i in range(200)]
    assert all(0.5 <= s <= 1.5 for s in samples)
