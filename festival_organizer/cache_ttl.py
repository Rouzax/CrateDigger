"""Shared TTL helpers for all persistent caches.

Every cache in the project calls into these helpers so expiry policy stays
uniform. Per-entry randomised TTL prevents synchronised expiry after a bulk
first-fetch.

Logging: no log lines emitted here; callers handle logging around cache ops.
"""
import hashlib
import random
import time


def jittered_ttl_seconds(base_days: int, jitter_pct: float = 0.2) -> float:
    """Return a randomised TTL in seconds around base_days (uniform +/- jitter_pct).

    Call this at every cache insert and stamp the result into entry["ttl"].
    Result lifetime spreads across [base * (1 - jitter_pct), base * (1 + jitter_pct)].
    """
    base_seconds = base_days * 86400
    factor = random.uniform(1.0 - jitter_pct, 1.0 + jitter_pct)
    return base_seconds * factor


def is_fresh(entry: dict, default_ttl_seconds: float) -> bool:
    """True if the entry was written less than its stamped TTL ago.

    Legacy entries without a "ttl" field fall back to default_ttl_seconds.
    Entries without "ts" are treated as stale.
    """
    ts = entry.get("ts")
    if ts is None:
        return False
    ttl = entry.get("ttl", default_ttl_seconds)
    return (time.time() - ts) < ttl


def hashed_jitter_factor(key: str, jitter_pct: float = 0.2) -> float:
    """Deterministic jitter factor in [1 - jitter_pct, 1 + jitter_pct] based on key.

    Use for filesystem-mtime caches that can't store a per-entry TTL field.
    Multiply the base TTL by this factor before comparing against file age.
    The same key always returns the same factor across runs, so a file doesn't
    flip-flop between fresh and stale.
    """
    digest = hashlib.md5(key.encode("utf-8")).digest()
    int_val = int.from_bytes(digest[:8], "big")
    unit = int_val / 0xFFFFFFFFFFFFFFFF  # [0, 1]
    return 1.0 + (unit - 0.5) * 2 * jitter_pct
