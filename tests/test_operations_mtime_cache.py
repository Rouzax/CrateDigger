"""Verify mtime-cache staleness uses deterministic hashed jitter."""
import os
import time
from pathlib import Path
from festival_organizer.operations import FanartOperation
from festival_organizer.config import Config


def _touch(path: Path, age_days: float) -> None:
    path.write_bytes(b"x")
    ts = time.time() - age_days * 86400
    os.utime(path, (ts, ts))


def test_is_stale_jitters_per_path(tmp_path):
    # Build a minimal Config; details don't matter for _is_stale.
    cfg = Config.__new__(Config)  # bypass __init__
    cfg._data = {"cache_ttl": {}}
    op = FanartOperation(config=cfg, library_root=tmp_path, ttl_days=90)

    # Create files at known ages relative to the base TTL.
    fresh_path = tmp_path / "fresh.jpg"
    stale_path = tmp_path / "stale.jpg"
    _touch(fresh_path, 70)   # well under 0.8 * 90 = 72 days
    _touch(stale_path, 110)  # well past 1.2 * 90 = 108 days
    assert op._is_stale(fresh_path) is False
    assert op._is_stale(stale_path) is True


def test_is_stale_deterministic(tmp_path):
    cfg = Config.__new__(Config)
    cfg._data = {"cache_ttl": {}}
    op = FanartOperation(config=cfg, library_root=tmp_path, ttl_days=90)
    path = tmp_path / "fixed.jpg"
    _touch(path, 95)  # inside jitter window 72-108 days
    r1 = op._is_stale(path)
    r2 = op._is_stale(path)
    assert r1 == r2  # same answer every call


def test_missing_file_is_stale(tmp_path):
    cfg = Config.__new__(Config)
    cfg._data = {"cache_ttl": {}}
    op = FanartOperation(config=cfg, library_root=tmp_path, ttl_days=90)
    assert op._is_stale(tmp_path / "does-not-exist.jpg") is True
