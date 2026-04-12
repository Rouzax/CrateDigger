# Per-Chapter Artist & Genre Tags Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Embed structured per-chapter `ARTIST` / `ARTIST_SLUGS` / `GENRE` tags in Matroska files using `TargetTypeValue=30` so TrackSplit can write accurate per-track FLAC tags; unify all artist references through `DjCache` canonical names; fix the synchronised-expiry problem in all five caches via a shared jittered-TTL helper; bump version 0.9.8 → 0.9.9.

**Architecture:** Extend the 1001TL tracklist HTML parser to produce structured `Track` rows (slug list + per-track genres). Add a shared `cache_ttl.py` utility that every cache calls into — per-entry `ttl` for JSON caches, deterministic hash jitter for filesystem-mtime caches. Teach `build_chapter_xml` / `mkv_tags` to emit and round-trip TTV=30 chapter-targeted tags through the existing `mkvpropedit` pipeline. Route all artist-name writes through `DjCache.canonical_name()`.

**Tech Stack:** Python 3.11+, pytest, Rich (existing progress UI), mkvpropedit/mkvextract/mkvmerge CLI (existing), lxml or stdlib ElementTree (existing patterns in `chapters.py`), BeautifulSoup (existing in `api.py`).

**Design doc:** `docs/plans/2026-04-12-per-chapter-tags-design.md`

---

## Pre-flight

Before starting, read:
- `docs/plans/2026-04-12-per-chapter-tags-design.md` (the design this plan implements)
- `.claude/docs/logging.md` (the project logging contract; every new log line must comply)
- `CLAUDE.md` (no em-dashes, no `Co-Authored-By` trailers)

Note: the class is `DjCache` (lowercase `j`), not `DJCache`. Several tasks reference it — match the existing casing exactly.

Work on branch `feat/per-chapter-tags` from `main`. Each task ends with a focused commit; don't batch multiple tasks into one commit.

---

## Task 1: Version bump

**Files:**
- Modify: `pyproject.toml` (the `version = "0.9.8"` line)

**Step 1: Update version**

Change `version = "0.9.8"` to `version = "0.9.9"` in `pyproject.toml`.

**Step 2: Verify**

Run: `grep -n '^version' pyproject.toml`
Expected: `version = "0.9.9"`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.9.9"
```

---

## Task 2: Shared `cache_ttl` helper — JSON-cache jitter

**Files:**
- Create: `festival_organizer/cache_ttl.py`
- Test: `tests/test_cache_ttl.py`

**Step 1: Write the failing tests**

```python
# tests/test_cache_ttl.py
"""Tests for the shared cache TTL helper."""
import time
import pytest
from festival_organizer.cache_ttl import jittered_ttl_seconds, is_fresh


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
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cache_ttl.py -v`
Expected: FAIL with `ModuleNotFoundError: festival_organizer.cache_ttl`.

**Step 3: Write minimal implementation**

```python
# festival_organizer/cache_ttl.py
"""Shared TTL helpers for all persistent caches.

Every cache in the project calls into these helpers so expiry policy stays
uniform. Per-entry randomised TTL prevents synchronised expiry after a bulk
first-fetch.

Logging: no log lines emitted here; callers handle logging around cache ops.
"""
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache_ttl.py -v`
Expected: all 7 tests PASS.

**Step 5: Commit**

```bash
git add festival_organizer/cache_ttl.py tests/test_cache_ttl.py
git commit -m "feat(cache): add shared jittered-TTL helper"
```

---

## Task 3: Shared `cache_ttl` helper — mtime-based jitter

**Files:**
- Modify: `festival_organizer/cache_ttl.py`
- Modify: `tests/test_cache_ttl.py`

Filesystem-mtime caches can't store a per-entry `ttl` field. Use a deterministic hash of the cache key so the same path always has the same effective TTL (stable across runs) but different paths spread across the jitter window.

**Step 1: Add the failing test**

Append to `tests/test_cache_ttl.py`:

```python
from festival_organizer.cache_ttl import hashed_jitter_factor


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
```

**Step 2: Run tests to verify new ones fail**

Run: `pytest tests/test_cache_ttl.py -v`
Expected: 4 new tests FAIL (name not defined), original 7 still pass.

**Step 3: Implement**

Append to `festival_organizer/cache_ttl.py`:

```python
import hashlib


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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache_ttl.py -v`
Expected: all 11 tests PASS.

**Step 5: Commit**

```bash
git add festival_organizer/cache_ttl.py tests/test_cache_ttl.py
git commit -m "feat(cache): add deterministic mtime-jitter helper"
```

---

## Task 4: Wire `DjCache` into shared helper + bump TTL to 90d

**Files:**
- Modify: `festival_organizer/tracklists/dj_cache.py` (lines 27-29, 48-49, 57-60)
- Test: `tests/tracklists/test_dj_cache.py` (create if missing)

**Step 1: Write the failing test**

```python
# tests/tracklists/test_dj_cache.py
"""Tests for DjCache TTL behaviour."""
import json
import time
from festival_organizer.tracklists.dj_cache import DjCache


def test_put_stamps_ttl_field(tmp_path):
    cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    cache.put("tiesto", {"name": "Tiesto"})
    raw = json.loads((tmp_path / "dj_cache.json").read_text())
    assert "ttl" in raw["tiesto"]
    # 90-day base with 20% jitter
    assert 90 * 86400 * 0.8 <= raw["tiesto"]["ttl"] <= 90 * 86400 * 1.2


def test_get_honours_per_entry_ttl(tmp_path):
    cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    # Write a stale entry manually: ts 200s ago, ttl 100s
    raw = {"tiesto": {"name": "Tiesto", "ts": time.time() - 200, "ttl": 100.0}}
    (tmp_path / "dj_cache.json").write_text(json.dumps(raw))
    cache._load()
    assert cache.get("tiesto") is None


def test_get_legacy_entry_uses_class_default(tmp_path):
    # Entry without "ttl" falls back to class default
    raw = {"tiesto": {"name": "Tiesto", "ts": time.time() - 10}}
    (tmp_path / "dj_cache.json").write_text(json.dumps(raw))
    cache = DjCache(cache_path=tmp_path / "dj_cache.json", ttl_days=90)
    assert cache.get("tiesto") is not None  # 10s < 90d default


def test_default_ttl_is_90_days():
    cache = DjCache(cache_path=None, ttl_days=90)  # default in signature
    assert cache._ttl_seconds == 90 * 86400
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/tracklists/test_dj_cache.py -v`
Expected: 3 FAIL (no `ttl` field written, entry-ttl not honoured), 1 PASS for now (default still 30d — will flip after change).

**Step 3: Modify `dj_cache.py`**

Change the default and rewire the freshness check and put:

```python
# At top of file, near other imports:
from festival_organizer.cache_ttl import jittered_ttl_seconds, is_fresh
```

Replace `__init__`:

```python
    def __init__(self, cache_path: Path | None = None, ttl_days: int = 90):
        self._path = cache_path or DEFAULT_PATH
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        self._load()
```

Replace `_is_fresh`:

```python
    def _is_fresh(self, entry: dict) -> bool:
        return is_fresh(entry, self._ttl_seconds)
```

Replace `put`:

```python
    def put(self, slug: str, entry: dict) -> None:
        entry["ts"] = time.time()
        entry["ttl"] = jittered_ttl_seconds(self._ttl_days)
        self._data[slug] = entry
        self._save()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/tracklists/test_dj_cache.py -v`
Expected: all 4 PASS.

**Step 5: Run the wider test suite to catch regressions**

Run: `pytest tests/ -x`
Expected: all existing tests still pass. If any test hardcoded `ttl_days=30`, update it to `90` or remove the assumption.

**Step 6: Commit**

```bash
git add festival_organizer/tracklists/dj_cache.py tests/tracklists/test_dj_cache.py
git commit -m "feat(dj-cache): jittered per-entry TTL, bump default to 90 days"
```

---

## Task 5: Wire `SourceCache` — TTL bump to 365d

**Files:**
- Modify: `festival_organizer/tracklists/source_cache.py` (lines 35-37, 56-57, 65-68)
- Test: `tests/tracklists/test_source_cache.py` (create if missing)

**Step 1: Write the failing test**

```python
# tests/tracklists/test_source_cache.py
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
    cache = SourceCache(cache_path=None)  # no args, use default
    assert cache._ttl_seconds == 365 * 86400
```

**Step 2: Run to verify fail**

Run: `pytest tests/tracklists/test_source_cache.py -v`
Expected: 4 FAIL.

**Step 3: Mirror the dj_cache.py changes**

Same three edits in `source_cache.py`:
- Change `__init__` default to `ttl_days: int = 365`, store both `self._ttl_days` and `self._ttl_seconds`.
- Add `from festival_organizer.cache_ttl import jittered_ttl_seconds, is_fresh` import.
- `_is_fresh` → `return is_fresh(entry, self._ttl_seconds)`.
- `put` → stamp `entry["ts"]` and `entry["ttl"] = jittered_ttl_seconds(self._ttl_days)`.

**Step 4: Run tests**

Run: `pytest tests/tracklists/test_source_cache.py tests/ -x`
Expected: all PASS.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/source_cache.py tests/tracklists/test_source_cache.py
git commit -m "feat(source-cache): jittered per-entry TTL, bump default to 365 days"
```

---

## Task 6: Wire `MBIDCache` — keep 90d default

**Files:**
- Modify: `festival_organizer/fanart.py` (lines 63-67, 91-92, 108-111)
- Test: `tests/test_fanart_cache.py` (create or extend existing)

**Step 1: Write the failing test**

```python
# tests/test_fanart_cache.py
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
    # Old bare-string format: value is a string, not a dict
    raw = {"afrojack": "bare-mbid-string"}
    (tmp_path / "mbid_cache.json").write_text(json.dumps(raw))
    cache = MBIDCache(cache_dir=tmp_path, ttl_days=90)
    assert not cache.has("Afrojack")  # ts=0 from migration → expired
```

**Step 2: Run to verify fail**

Run: `pytest tests/test_fanart_cache.py -v`
Expected: 2 FAIL (missing ttl field, entry-ttl not honoured). Third may already pass.

**Step 3: Modify `fanart.py`**

Add import at top: `from festival_organizer.cache_ttl import jittered_ttl_seconds, is_fresh`.

Store the days value in `__init__`:

```python
    def __init__(self, cache_dir: Path | None = None, ttl_days: int = 90):
        self._dir = cache_dir or (Path.home() / ".cratedigger")
        self._path = self._dir / "mbid_cache.json"
        self._ttl_days = ttl_days
        self._ttl_seconds = ttl_days * 86400
        self._data: dict[str, dict] = {}
        self._load()
```

Replace `_is_fresh`:

```python
    def _is_fresh(self, entry: dict) -> bool:
        return is_fresh(entry, self._ttl_seconds)
```

Replace `put`:

```python
    def put(self, artist: str, mbid: str | None) -> None:
        """Cache an artist-to-MBID mapping. None = not found (negative cache)."""
        self._data[artist.lower()] = {
            "mbid": mbid,
            "ts": time.time(),
            "ttl": jittered_ttl_seconds(self._ttl_days),
        }
        self._save()
```

**Step 4: Run tests**

Run: `pytest tests/test_fanart_cache.py tests/ -x`
Expected: all PASS.

**Step 5: Commit**

```bash
git add festival_organizer/fanart.py tests/test_fanart_cache.py
git commit -m "feat(mbid-cache): jittered per-entry TTL"
```

---

## Task 7: Wire mtime-based caches in `operations.py`

**Files:**
- Modify: `festival_organizer/operations.py` (lines 321-354 `_download_artwork`, lines 356-~400 `_download_dj_artwork`, lines 658-663 `_is_stale`)
- Test: `tests/test_operations_mtime_cache.py` (new)

**Step 1: Write the failing test**

```python
# tests/test_operations_mtime_cache.py
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


def test_is_stale_jitters_per_path(tmp_path, monkeypatch):
    # Build a minimal Config; details don't matter for _is_stale.
    cfg = Config.__new__(Config)  # bypass __init__
    cfg._data = {"cache_ttl": {}}
    op = FanartOperation(config=cfg, library_root=tmp_path, ttl_days=90)

    # Create files aged exactly 90 days — right at the base boundary.
    fresh_path = tmp_path / "fresh.jpg"
    stale_path = tmp_path / "stale.jpg"
    _touch(fresh_path, 89.9)  # just under base
    _touch(stale_path, 110)   # well past 1.2x base (108)
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
```

**Step 2: Run to verify fail**

Run: `pytest tests/test_operations_mtime_cache.py -v`
Expected: at least 1 FAIL — the fresh-boundary case depends on the hashed jitter factor landing near 1.0, which un-jittered code won't guarantee across different names. (If by coincidence it passes, the determinism test will still pass but the jitter wiring will still be missing; proceed to step 3.)

**Step 3: Modify `operations.py`**

Add import at top: `from festival_organizer.cache_ttl import hashed_jitter_factor`.

Replace `FanartOperation._is_stale` (around line 658):

```python
    def _is_stale(self, path: Path) -> bool:
        """Check if a cached file is missing or older than jittered TTL."""
        if not path.exists():
            return True
        age_days = (time.time() - path.stat().st_mtime) / 86400
        effective_ttl = self._ttl_days * hashed_jitter_factor(path.name)
        return age_days > effective_ttl
```

Inside `AlbumPosterOperation._download_artwork` (around lines 331-336), replace:

```python
        if cached.exists():
            age_days = (time.time() - cached.stat().st_mtime) / 86400
            effective_ttl = self._ttl_days * hashed_jitter_factor(cached.name)
            if age_days <= effective_ttl:
                return cached
            cached.unlink()
            logger.debug("Stale artwork cache (%d days, ttl %.1f): %s",
                         int(age_days), effective_ttl, cached.name)
```

Apply the same three-line change inside `AlbumPosterOperation._download_dj_artwork` (around lines 362-367): compute `effective_ttl` from `hashed_jitter_factor(cached.name)` (or `artist` — pick one and stay consistent within the function) and compare against that.

**Step 4: Run tests**

Run: `pytest tests/test_operations_mtime_cache.py tests/ -x`
Expected: all PASS.

**Step 5: Commit**

```bash
git add festival_organizer/operations.py tests/test_operations_mtime_cache.py
git commit -m "feat(mtime-cache): hashed jitter for per-path TTL"
```

---

## Task 8: `Track` dataclass + `TracklistExport.tracks` extension

**Files:**
- Modify: `festival_organizer/tracklists/api.py` (find the `TracklistExport` dataclass near line 56-67 and add the new field; add the `Track` dataclass above it)
- Test: `tests/tracklists/test_models.py` (new or existing)

**Step 1: Write the failing test**

```python
# tests/tracklists/test_models.py
from festival_organizer.tracklists.api import Track, TracklistExport


def test_track_fields():
    t = Track(start_ms=120_000, raw_text="AFROJACK - ID",
              artist_slugs=["afrojack"], genres=["House"])
    assert t.start_ms == 120_000
    assert t.raw_text == "AFROJACK - ID"
    assert t.artist_slugs == ["afrojack"]
    assert t.genres == ["House"]


def test_tracklist_export_has_tracks_field():
    te = TracklistExport(lines=[], genres=[], dj_artists=[], stage_text="",
                         sources_by_type={}, country="", tracks=[])
    assert te.tracks == []


def test_tracklist_export_tracks_defaults_to_empty():
    # tracks field should have a default_factory so existing call sites keep working
    te = TracklistExport(lines=[], genres=[], dj_artists=[], stage_text="",
                         sources_by_type={}, country="")
    assert te.tracks == []
```

**Step 2: Run to verify fail**

Run: `pytest tests/tracklists/test_models.py -v`
Expected: FAIL — `Track` import fails.

**Step 3: Add `Track` and extend `TracklistExport`**

In `festival_organizer/tracklists/api.py`, above the `TracklistExport` dataclass (line 56-ish), add:

```python
@dataclass
class Track:
    """A single track on a 1001TL tracklist.

    start_ms: chapter start in milliseconds
    raw_text: the visible track label, as exported by 1001TL (e.g. 'Artist - Title (Remix) [Label]')
    artist_slugs: 1001TL slugs for every linked artist on the track row, in link order
    genres: per-track <meta itemprop="genre"> values for this row
    """
    start_ms: int
    raw_text: str
    artist_slugs: list[str]
    genres: list[str]
```

Extend `TracklistExport` (same file, existing dataclass) with a new field:

```python
    tracks: list[Track] = field(default_factory=list)
```

Make sure `field` is imported from `dataclasses` at the top of the file.

**Step 4: Run tests**

Run: `pytest tests/tracklists/test_models.py tests/ -x`
Expected: all PASS. Existing tests that build `TracklistExport` without `tracks` still work because of `default_factory`.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/api.py tests/tracklists/test_models.py
git commit -m "feat(tracklist): add Track dataclass and TracklistExport.tracks field"
```

---

## Task 9: Per-track HTML parser

**Validated against saved fixture `tests/tracklists/fixtures/afrojack_edc_2025.html` (already committed).**

**Key findings from fixture probe:**
- Track rows: `div.tlpItem` — 77 total on the Afrojack page.
- **Only 27 rows are chapter-aligned**: those with class `tlpTog` (not `tlpSubTog`) and no `con` class. The rest are sub-tracks shown underneath mashups. Plus the very first row is always at 0:00 (`trRow1`, often no `con`).
- **Authoritative rule:** a row is chapter-aligned iff `tlpTog` is in its class list AND `con` is NOT AND `tlpSubTog` is NOT. Filter on class list, not on cue_seconds.
- Each row has `<input id="tlpN_cue_seconds" value="SECONDS_FLOAT">`. For chapter-aligned rows this is the track start in seconds (float, can be 0.0 for the intro). Multiply by 1000 for start_ms.
- Per-row metadata: `<meta itemprop="name" content="ARTIST - TITLE">`, `<meta itemprop="genre" content="...">` (0+ per row), `<meta itemprop="duration" content="PT..">`. **Duration is per-track time, not chapter length.**
- Per-row artist links: `<a href="/artist/<id>/<slug>/index.html">`. Slug is path segment 3. NOT `/dj/<slug>/` — that form only appears in H1 set-owner region.

**Files:**
- Modify: `festival_organizer/tracklists/api.py` — add `_parse_tracks(html)` helper that returns `list[Track]` for chapter-aligned rows only.
- Test: `tests/tracklists/test_parse_tracks.py` (new)
- Fixture: already committed at `tests/tracklists/fixtures/afrojack_edc_2025.html`.

**Step 1: Write the failing test**

```python
# tests/tracklists/test_parse_tracks.py
from pathlib import Path
from festival_organizer.tracklists.api import _parse_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "afrojack_edc_2025.html"


def test_parse_tracks_returns_chapter_aligned_rows_only():
    """HTML has 77 tlpItem rows but only ~27-30 are chapter-aligned."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # Afrojack EDC 2025 set has 27 rows with cue_seconds > 0 and 1 intro at 0.
    # Expect 27-30, reject 77 (which would mean we didn't filter sub-rows).
    assert 24 <= len(tracks) <= 35


def test_parse_tracks_extracts_slugs():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # First track is AFROJACK - Take Over Control; its slug is 'afrojack'.
    assert tracks[0].artist_slugs
    assert tracks[0].artist_slugs[0] == "afrojack"
    # At least 80% of chapter-aligned rows have at least one slug
    with_slugs = [t for t in tracks if t.artist_slugs]
    assert len(with_slugs) >= int(len(tracks) * 0.8)


def test_parse_tracks_extracts_genres_from_chapter_rows():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    # Chapter-aligned rows alone should have a reasonable genre count
    # (sub-rows being excluded reduces noise).
    all_genres = [g for t in tracks for g in t.genres]
    assert len(all_genres) >= 5


def test_parse_tracks_start_ms_monotonic():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    starts = [t.start_ms for t in tracks]
    assert starts == sorted(starts)


def test_parse_tracks_first_chapter_at_zero():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert tracks[0].start_ms == 0


def test_parse_tracks_raw_text_preserved():
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    assert "Take Over Control" in tracks[0].raw_text


def test_parse_tracks_no_mojibake():
    """After the 1e45b59 fix, no parsed text should contain mojibake bytes."""
    tracks = _parse_tracks(FIXTURE.read_text(encoding="utf-8"))
    for t in tracks:
        assert "├" not in t.raw_text, f"mojibake in {t.raw_text!r}"
        for g in t.genres:
            assert "├" not in g
```

**Step 2: Run to verify fail**

Run: `python3 -m pytest tests/tracklists/test_parse_tracks.py -v`
Expected: FAIL — `_parse_tracks` not defined.

**Step 3: Implement `_parse_tracks`**

In `festival_organizer/tracklists/api.py`, add a module-level helper below the existing parse helpers. Use BeautifulSoup4 (now a project dep via `pyproject.toml`).

```python
def _parse_tracks(html: str) -> list["Track"]:
    """Extract chapter-aligned per-track rows from a 1001TL tracklist page.

    Only rows with class 'tlpTog' and NOT 'con' and NOT 'tlpSubTog' are
    included, because the page also contains mashup-component sub-rows that
    don't correspond to chapter atoms. Returns Track objects in page order
    with start_ms taken from the row's cue_seconds input (float seconds).
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    tracks: list[Track] = []
    for row in soup.select("div.tlpItem"):
        classes = set(row.get("class", []))
        if "tlpTog" not in classes:
            continue
        if "con" in classes or "tlpSubTog" in classes:
            continue
        cue_el = row.select_one("input[id$='_cue_seconds']")
        if cue_el is None:
            continue
        try:
            start_ms = int(float(cue_el.get("value", "0")) * 1000)
        except ValueError:
            continue
        name_meta = row.select_one('meta[itemprop="name"]')
        raw_text = name_meta.get("content", "") if name_meta else ""
        genres = [
            m.get("content", "")
            for m in row.select('meta[itemprop="genre"]')
            if m.get("content")
        ]
        slugs: list[str] = []
        for a in row.select("a[href^='/artist/']"):
            m = re.match(r"/artist/[^/]+/([^/]+)/", a.get("href", ""))
            if m and m.group(1) not in slugs:
                slugs.append(m.group(1))
        tracks.append(
            Track(
                start_ms=start_ms,
                raw_text=raw_text,
                artist_slugs=slugs,
                genres=genres,
            )
        )
    return tracks
```

No need for `TRACK_ROW_SELECTOR`, `_parse_timestamp_to_ms`, `_slug_from_dj_href` constants as separate helpers — the parser is short enough that inlining is clearer. Do not add BeautifulSoup-based parsing to the existing `_extract_genres` or other scrapes; they already work.

Wire into `export_tracklist`: after the existing HTML-enrichment block (line ~165), call `tracks = _parse_tracks(page_resp.text)` and populate `TracklistExport.tracks = tracks` on the return.

**Step 4: Run tests**

Run: `python3 -m pytest tests/tracklists/test_parse_tracks.py tests/ -x`
Expected: all new tests PASS, full suite still green.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/api.py tests/tracklists/test_parse_tracks.py
git commit -m "feat(tracklist): parse per-track slugs and genres from HTML"
```

**Notes:**
- The chapter-aligned row filter (`tlpTog AND NOT con AND NOT tlpSubTog`) is the authoritative rule confirmed against the Afrojack EDC 2025 fixture. Alternative approaches (`cue_seconds > 0`, trno ranges) were rejected because the intro row has `cue_seconds=0` and trno 0, and sub-rows don't have distinct trno values.
- **Mainstage noise:** "Mainstage" still appears in chapter-aligned rows' genre metas on this fixture (1001TL tags stage names as per-track genres). Task 9a's top-N aggregator will surface it. If that becomes a UX problem, Task 14 can wrap the aggregator with a stage-name blocklist derived from `source_cache`; not doing it in Task 9a keeps the aggregator a pure function.

---

## Task 9a: Top-N genre aggregator

**Files:**
- Modify: `festival_organizer/tracklists/api.py` — add a module-level helper `top_genres_by_frequency(tracks, n=5)`.
- Test: `tests/tracklists/test_top_genres.py` (new)

Context: the current `_extract_genres` scrape returns a deduped union of every per-track `<meta itemprop="genre">` on the page (see `api.py:538-555`) — typically 10-15 genres for a 30-track set, most of them long-tail noise. Now that Task 9 gives us structured per-track genres, we can compute a dominant-genre fingerprint instead. Used to populate `CRATEDIGGER_1001TL_GENRES` in Task 14.

**Step 1: Write the failing tests**

```python
# tests/tracklists/test_top_genres.py
from festival_organizer.tracklists.api import Track, top_genres_by_frequency


def _track(genres):
    return Track(start_ms=0, raw_text="x", artist_slugs=[], genres=genres)


def test_top_genres_counts_per_track_occurrences():
    tracks = [
        _track(["House"]),
        _track(["House", "Tech House"]),
        _track(["Techno"]),
        _track(["House"]),
    ]
    # House=3, Tech House=1, Techno=1 → House first, then ties by first appearance
    result = top_genres_by_frequency(tracks, n=5)
    assert result[0] == "House"
    assert set(result) == {"House", "Tech House", "Techno"}


def test_top_genres_respects_n():
    tracks = [_track([f"G{i}"]) for i in range(10)]
    result = top_genres_by_frequency(tracks, n=3)
    assert len(result) == 3


def test_top_genres_ties_broken_by_first_appearance():
    tracks = [_track(["B"]), _track(["A"]), _track(["B"]), _track(["A"])]
    # A=2, B=2 — both tied. First-appearance order: B before A.
    result = top_genres_by_frequency(tracks, n=5)
    assert result == ["B", "A"]


def test_top_genres_empty():
    assert top_genres_by_frequency([], n=5) == []


def test_top_genres_skips_blank():
    tracks = [_track(["", "House", ""])]
    assert top_genres_by_frequency(tracks, n=5) == ["House"]
```

**Step 2: Run to verify fail**

Run: `pytest tests/tracklists/test_top_genres.py -v`
Expected: FAIL — `top_genres_by_frequency` not defined.

**Step 3: Implement**

In `festival_organizer/tracklists/api.py`:

```python
def top_genres_by_frequency(tracks: list["Track"], n: int = 5) -> list[str]:
    """Return the top-n most frequent per-track genres across the set.

    Each genre counts once per track it appears on (so a track tagged with
    three genres contributes one to each). Ties are broken by first-appearance
    order so the result is deterministic across runs.
    """
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    idx = 0
    for track in tracks:
        for g in track.genres:
            if not g:
                continue
            if g not in counts:
                first_seen[g] = idx
                idx += 1
            counts[g] = counts.get(g, 0) + 1
    ordered = sorted(counts, key=lambda g: (-counts[g], first_seen[g]))
    return ordered[:n]
```

**Step 4: Run tests**

Run: `pytest tests/tracklists/test_top_genres.py tests/ -x`
Expected: all PASS.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/api.py tests/tracklists/test_top_genres.py
git commit -m "feat(tracklist): top-N genre aggregator for set-level GENRES tag"
```

---

## Task 10: `DjCache.get_or_fetch_many` batch helper with Rich progress

**Files:**
- Modify: `festival_organizer/tracklists/dj_cache.py` — add `get_or_fetch_many`.
- Modify: wherever the existing single-DJ fetcher lives (grep for `dj_cache` usages in `api.py` or `tracklists/cli_handler.py` to find the current `get_or_fetch` entry point — reuse it for the per-slug fetch inside the loop).
- Test: `tests/tracklists/test_dj_cache_batch.py` (new)

**Step 1: Write the failing test**

```python
# tests/tracklists/test_dj_cache_batch.py
from unittest.mock import MagicMock
from festival_organizer.tracklists.dj_cache import DjCache


def test_get_or_fetch_many_hits_cache(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})
    cache.put("tiesto", {"name": "Tiesto"})
    fetcher = MagicMock()
    result = cache.get_or_fetch_many(["afrojack", "tiesto"], fetcher=fetcher)
    assert result["afrojack"]["name"] == "Afrojack"
    assert result["tiesto"]["name"] == "Tiesto"
    fetcher.assert_not_called()


def test_get_or_fetch_many_fetches_misses(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})

    def fetcher(slug: str) -> dict:
        return {"name": slug.title()}

    result = cache.get_or_fetch_many(["afrojack", "newdj"], fetcher=fetcher)
    assert result["afrojack"]["name"] == "Afrojack"
    assert result["newdj"]["name"] == "Newdj"
    # Was stamped into cache
    assert cache.get("newdj")["name"] == "Newdj"


def test_get_or_fetch_many_skips_failed_fetches(tmp_path, caplog):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)

    def fetcher(slug: str) -> dict | None:
        return None if slug == "gone" else {"name": slug.title()}

    result = cache.get_or_fetch_many(["gone", "ok"], fetcher=fetcher)
    assert "gone" not in result
    assert result["ok"]["name"] == "Ok"


def test_get_or_fetch_many_dedupes_input(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    calls = []

    def fetcher(slug: str) -> dict:
        calls.append(slug)
        return {"name": slug.title()}

    cache.get_or_fetch_many(["a", "a", "b", "a"], fetcher=fetcher)
    assert sorted(calls) == ["a", "b"]  # each fetched once
```

**Step 2: Run to verify fail**

Run: `pytest tests/tracklists/test_dj_cache_batch.py -v`
Expected: all 4 FAIL — `get_or_fetch_many` not defined.

**Step 3: Implement**

In `dj_cache.py`:

```python
    def get_or_fetch_many(
        self,
        slugs,
        fetcher,
        progress=None,
    ) -> dict[str, dict]:
        """Resolve a batch of slugs, fetching any not in cache via fetcher(slug).

        Parameters
        ----------
        slugs : iterable of str
            Slugs to resolve. Duplicates are deduped.
        fetcher : callable[str, dict | None]
            Called for every slug not present in the cache. Should respect the
            5s 1001TL throttle (reuse TracklistSession.throttle). Returns a
            profile dict (will be put into the cache) or None (skipped with a
            WARNING-level log).
        progress : optional callable[str, int, int]
            Called as progress(current_slug, done_count, total_misses) after each
            fetch so callers can drive a Rich progress display.

        Returns
        -------
        dict[str, dict]
            Resolved entries keyed by slug. Slugs that failed to fetch are omitted.
        """
        unique = list(dict.fromkeys(slugs))  # dedupe, preserve order
        resolved: dict[str, dict] = {}
        misses: list[str] = []
        for slug in unique:
            hit = self.get(slug)
            if hit is not None:
                resolved[slug] = hit
            else:
                misses.append(slug)

        for i, slug in enumerate(misses, start=1):
            try:
                entry = fetcher(slug)
            except Exception as exc:
                logger.warning("Artist fetch failed for slug '%s': %s", slug, exc)
                continue
            if entry is None:
                logger.warning("Artist fetch returned no data for slug '%s'", slug)
                continue
            self.put(slug, entry)
            resolved[slug] = entry
            if progress is not None:
                progress(slug, i, len(misses))
        return resolved
```

**Step 4: Run tests**

Run: `pytest tests/tracklists/test_dj_cache_batch.py -v`
Expected: all PASS.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/dj_cache.py tests/tracklists/test_dj_cache_batch.py
git commit -m "feat(dj-cache): get_or_fetch_many batch helper"
```

---

## Task 11: `DjCache.canonical_name` helper

**Files:**
- Modify: `festival_organizer/tracklists/dj_cache.py`
- Test: extend `tests/tracklists/test_dj_cache.py`

**Step 1: Write the failing test**

Append to `tests/tracklists/test_dj_cache.py`:

```python
def test_canonical_name_resolves(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    cache.put("afrojack", {"name": "Afrojack"})
    assert cache.canonical_name("afrojack") == "Afrojack"


def test_canonical_name_falls_back_to_given(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    # Slug not in cache — return the slug itself (caller can choose to display raw)
    assert cache.canonical_name("unknown") == "unknown"


def test_canonical_name_fallback_value(tmp_path):
    cache = DjCache(cache_path=tmp_path / "c.json", ttl_days=90)
    assert cache.canonical_name("unknown", fallback="X") == "X"
```

**Step 2: Run to verify fail**

Run: `pytest tests/tracklists/test_dj_cache.py -v -k canonical`
Expected: 3 FAIL.

**Step 3: Implement**

Add to `DjCache`:

```python
    def canonical_name(self, slug: str, fallback: str | None = None) -> str:
        """Return the canonical name for a slug, or fallback/slug when unknown."""
        entry = self._data.get(slug)
        if entry and entry.get("name"):
            return entry["name"]
        return fallback if fallback is not None else slug
```

**Step 4: Run tests**

Run: `pytest tests/tracklists/test_dj_cache.py -v`
Expected: all PASS.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/dj_cache.py tests/tracklists/test_dj_cache.py
git commit -m "feat(dj-cache): add canonical_name helper"
```

---

## Task 12: TTV=30 support in `mkv_tags.py`

**Files:**
- Modify: `festival_organizer/mkv_tags.py` — teach `read_merged_tags` / `write_merged_tags` to handle a TTV=30 scope keyed by `ChapterUID`.
- Test: `tests/test_mkv_tags_ttv30.py` (new)

**Step 1: Read current tag code**

Run: `grep -n 'TargetTypeValue\|TTV\|50\|70' festival_organizer/mkv_tags.py` — then read the two functions end-to-end. Understand how the current merge distinguishes TTV=50 vs 70 and how the XML is produced. You'll mirror that pattern for 30.

**Step 2: Write the failing test**

```python
# tests/test_mkv_tags_ttv30.py
"""Round-trip chapter-targeted (TTV=30) tags via mkvpropedit."""
import shutil
import subprocess
from pathlib import Path
import pytest
from festival_organizer.mkv_tags import build_tags_xml, parse_tags_xml


def test_build_tags_xml_includes_ttv30_with_chapter_uid(tmp_path):
    xml = build_tags_xml({
        50: {"ARTIST": "Afrojack"},
        30: {
            12345678901234567890: {"ARTIST": "Afrojack", "GENRE": "House"},
            98765432109876543210: {"ARTIST": "Guest", "GENRE": "Techno"},
        },
    })
    assert "<TargetTypeValue>30</TargetTypeValue>" in xml
    assert "<ChapterUID>12345678901234567890</ChapterUID>" in xml
    assert "<ChapterUID>98765432109876543210</ChapterUID>" in xml


def test_parse_tags_xml_round_trip(tmp_path):
    original = {
        50: {"ARTIST": "Afrojack"},
        30: {
            111: {"ARTIST": "A", "GENRE": "House"},
            222: {"ARTIST": "B", "GENRE": "Techno"},
        },
    }
    xml = build_tags_xml(original)
    parsed = parse_tags_xml(xml)
    assert parsed[50]["ARTIST"] == "Afrojack"
    assert parsed[30][111]["ARTIST"] == "A"
    assert parsed[30][111]["GENRE"] == "House"
    assert parsed[30][222]["ARTIST"] == "B"


@pytest.mark.skipif(shutil.which("mkvpropedit") is None, reason="mkvpropedit required")
def test_mkvpropedit_accepts_ttv30_xml(tmp_path):
    # Build a tiny 1-second black-frame MKV first with ffmpeg, if available,
    # or fetch a small fixture from tests/fixtures/empty.mkv (commit one).
    src = Path(__file__).parent / "fixtures" / "empty.mkv"
    if not src.exists():
        pytest.skip("no empty.mkv fixture")
    target = tmp_path / "empty.mkv"
    shutil.copy(src, target)

    # Add a chapter with a known UID via mkvpropedit first...
    # Then write our TTV=30 tags file targeting that ChapterUID and verify mkvpropedit applies it.
    # (Full wiring for the integration test happens in Task 19; this step just confirms
    # build_tags_xml produces syntactically valid XML mkvpropedit will accept.)
    xml_path = tmp_path / "tags.xml"
    xml_path.write_text(build_tags_xml({30: {1234: {"ARTIST": "X"}}}))
    # mkvpropedit --tags all:<file> just loads and validates XML; invalid XML exits non-zero.
    result = subprocess.run(
        ["mkvpropedit", str(target), "--tags", f"all:{xml_path}"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
```

**Step 3: Run to verify fail**

Run: `pytest tests/test_mkv_tags_ttv30.py -v`
Expected: first two FAIL (builder doesn't emit TTV=30; parser returns wrong shape). Third skipped if no fixture or mkvpropedit.

**Step 4: Implement**

In `festival_organizer/mkv_tags.py`, modify `build_tags_xml` (or equivalent) to accept a `dict[int, ...]` where the value shape depends on the TTV:
- For 50 and 70: `dict[str, str]` — attribute name → value (existing behaviour).
- For 30: `dict[int, dict[str, str]]` — `ChapterUID` → (attribute name → value).

For each TTV=30 entry, emit one `<Tag>` block with:

```xml
<Tag>
  <Targets>
    <TargetTypeValue>30</TargetTypeValue>
    <TargetType>CHAPTER</TargetType>
    <ChapterUID>{uid}</ChapterUID>
  </Targets>
  <Simple><Name>ARTIST</Name><String>...</String></Simple>
  ...
</Tag>
```

Mirror the read/merge side: `parse_tags_xml` returns the two-level dict for TTV=30.

Preserve any existing TTV=30 tags found in the file during the extract-merge-write cycle — the user may have hand-annotated chapters.

**Step 5: Run tests**

Run: `pytest tests/test_mkv_tags_ttv30.py tests/ -x`
Expected: all PASS (or skipped where appropriate).

**Step 6: Commit**

```bash
git add festival_organizer/mkv_tags.py tests/test_mkv_tags_ttv30.py tests/fixtures/empty.mkv
git commit -m "feat(mkv-tags): round-trip TTV=30 chapter-targeted tags"
```

---

## Task 13: `build_chapter_xml` accepts `per_chapter_tags`

**Files:**
- Modify: `festival_organizer/tracklists/chapters.py` — `build_chapter_xml` gains an optional `per_chapter_tags: dict[int, dict[str, str]] | None = None` arg. Just wires through to `build_tags_xml` via the caller; the chapter XML itself doesn't change (tags go in a separate file for `mkvpropedit --tags`).
- Modify: `embed_chapters` — accept `per_chapter_tags` and pass them alongside the existing global/collection tags when calling `write_merged_tags`.
- Test: `tests/tracklists/test_chapters_per_chapter_tags.py` (new)

**Step 1: Write the failing test**

```python
# tests/tracklists/test_chapters_per_chapter_tags.py
from festival_organizer.tracklists.chapters import build_chapter_xml


def test_build_chapter_xml_assigns_stable_uids():
    atoms = [(0, "Intro"), (60_000, "Track 1"), (180_000, "Track 2")]
    xml1 = build_chapter_xml(atoms)
    xml2 = build_chapter_xml(atoms)
    # ChapterUIDs are random, so XML bytes differ across builds...
    # BUT within a single build, the same atom order gives monotonic UIDs.
    # The real contract is: the list of UIDs we'd want to tag must be retrievable.
    # If build_chapter_xml returns a (xml, uids) tuple, the test asserts that shape.
    # (This assertion forces the implementation to expose UIDs for tagging.)
    xml, uids = build_chapter_xml(atoms, return_uids=True)
    assert len(uids) == 3
    assert all(isinstance(u, int) and u > 0 for u in uids)
```

**Step 2: Run to verify fail**

Run: `pytest tests/tracklists/test_chapters_per_chapter_tags.py -v`
Expected: FAIL — `return_uids` arg not supported or tuple shape wrong.

**Step 3: Modify `build_chapter_xml`**

Add `return_uids: bool = False` parameter. When true, return `(xml_str, uids)` where `uids` is the list of `ChapterUID` values in the same order as the input atoms. This lets the caller map atom index → UID → per-chapter tags.

Keep the default behaviour (bare XML string) for existing callers.

**Step 4: Run tests**

Run: `pytest tests/tracklists/test_chapters_per_chapter_tags.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/chapters.py tests/tracklists/test_chapters_per_chapter_tags.py
git commit -m "feat(chapters): expose ChapterUIDs for per-chapter tagging"
```

---

## Task 14: Orchestration — resolve slugs during enrichment, write TTV=30 tags

**Files:**
- Modify: `festival_organizer/metadata.py` (or whichever module composes the tag payload passed to `write_merged_tags`). Grep for `CRATEDIGGER_1001TL_ARTISTS` to find the composition point.
- Modify: the enrichment pipeline around `export_tracklist` and `embed_chapters` — after parsing, collect all per-track slugs + set-owner slugs, call `cache.get_or_fetch_many(...)`, then build the per-chapter tag map.
- Test: `tests/test_enrichment_per_chapter.py` (new; integration-style with mocked fetcher)

**Step 1: Write the failing test**

```python
# tests/test_enrichment_per_chapter.py
"""Integration: full enrichment pipeline emits TTV=30 tags with canonical names."""
from unittest.mock import MagicMock
# Import whichever function orchestrates enrichment. If it's `enrich_file`
# in metadata.py, import it. Adjust based on what you find when grepping.
# ...


def test_enrichment_resolves_canonical_artist_in_set_tag(...):
    """CRATEDIGGER_1001TL_ARTISTS uses DjCache canonical, not 1001TL H1."""
    # Arrange: mock session + cache returning {"afrojack": {"name": "Afrojack"}}
    # Act: run enrichment against a fixture set whose H1 is "AFROJACK"
    # Assert: the composed tag payload at TTV=70 has ARTIST == "Afrojack"


def test_enrichment_emits_ttv30_per_chapter(...):
    """Every chapter atom gets a matching TTV=30 tag block."""
    # Arrange: fixture tracklist with 3 tracks, each with a known slug and genre
    # Act: run enrichment
    # Assert: the tag payload has a dict at key 30, len == 3, each entry has
    # ARTIST / ARTIST_SLUGS / GENRE keys


def test_enrichment_set_owner_token_normalised_in_chapter_titles(...):
    """'AFROJACK - ID' chapter titles become 'Afrojack - ID'."""
    # Arrange: fixture with two chapters:
    #    "AFROJACK - ID"                (set owner token, should normalise)
    #    "Armin van Buuren - Blah"      (different artist, leave alone)
    # Act: run enrichment
    # Assert: first chapter title == "Afrojack - ID", second unchanged
```

Fill in the exact imports and arrangement based on what you find in `metadata.py` / `operations.py` — the integration surface area is code you're about to read, not guess at.

**Step 2: Run to verify fail**

Run: `pytest tests/test_enrichment_per_chapter.py -v`
Expected: all FAIL.

**Step 3: Implement the orchestration changes**

1. After `export_tracklist()` returns a `TracklistExport` with `tracks`, collect `set_owner_slugs` (from `dj_artists`) and `track_slugs` (union over `tracks[i].artist_slugs`).
2. Build the fetcher closure that calls the existing single-artist scraper inside `TracklistSession` (grep for where `dj_cache.put` is currently called — reuse that call path). The closure enforces the 5s throttle via the same `session.throttle()` already in use.
3. `cache.get_or_fetch_many(union_of_slugs, fetcher, progress=...)` with `progress` wired to a Rich progress counter (see Task 15).
4. When composing `CRATEDIGGER_1001TL_ARTISTS` (at the current composition site in `metadata.py`), route through `cache.canonical_name(slug)` for each set-owner slug; join with `|` (pipe) for multi-DJ sets — matches the existing convention in all 79 enriched files (`Armin van Buuren|KI/KI`, `AFROJACK|R3HAB`, `Agents Of Time|MORTEN`). Same separator used by `CRATEDIGGER_1001TL_GENRES` and the new per-chapter `ARTIST_SLUGS` for consistency.
4b. **Alias resolution chain.** Some 1001TL set-owner slugs are aliases of a different canonical artist (real example: the 1001TL page shows `SOMETHING ELSE` but `SOMETHING ELSE` is an alias of canonical `ALOK` in `artists.json`). Before stamping `CRATEDIGGER_1001TL_ARTISTS`, feed `DjCache.canonical_name(slug)` output through the existing `artists.json` alias resolver (grep for where the top-level `ARTIST` tag is composed — that code already does this resolution). This ensures `ARTIST` and `CRATEDIGGER_1001TL_ARTISTS` end up pointing at the same canonical name. Write a test for the `SOMETHING ELSE → ALOK` case using that set as a fixture.
4a. When composing `CRATEDIGGER_1001TL_GENRES` (same composition site), prefer `top_genres_by_frequency(tracks, n=5)` pipe-joined. If the parser yielded zero per-track genres (HTML shape change, empty tracklist), fall back to the existing `_extract_genres` union-deduped list so enrichment never produces an empty genre tag. Add a corresponding test in `tests/test_enrichment_per_chapter.py`:

```python
def test_set_level_genres_uses_top5(...):
    # Fixture: 10 tracks with genres distributed so "House" wins count
    # Assert: TTV=70 GENRES tag == "House|Tech House|Techno|..." (top 5)
    # Assert: len(GENRES.split("|")) <= 5


def test_set_level_genres_falls_back_when_no_per_track_data(...):
    # Fixture: tracklist where per-track parse yields no genres
    # Assert: GENRES still populated via legacy union-deduped scrape
```
5. When building chapter display strings, if the first token matches the 1001TL set-owner display form (upper-case of `canonical_name`), swap it for `canonical_name`. Leave the rest of the string alone.
6. Build the per-chapter tag map keyed by `ChapterUID` (from Task 13's `return_uids=True` call): for each track, `{ChapterUID: {"ARTIST": cache.canonical_name(track.artist_slugs[0]) if track.artist_slugs else "", "ARTIST_SLUGS": "|".join(track.artist_slugs), "GENRE": "|".join(track.genres)}}`. Skip chapters whose track has no data. Pipe separator keeps the new tag consistent with `CRATEDIGGER_1001TL_ARTISTS` and `CRATEDIGGER_1001TL_GENRES`.
7. Pass this dict as the TTV=30 scope to `write_merged_tags`.

**Step 4: Run tests**

Run: `pytest tests/test_enrichment_per_chapter.py tests/ -x`
Expected: all PASS, no regressions.

**Step 5: Commit**

```bash
git add festival_organizer/metadata.py festival_organizer/tracklists/api.py festival_organizer/tracklists/chapters.py tests/test_enrichment_per_chapter.py
git commit -m "feat(enrichment): per-chapter tags and canonical artist names"
```

---

## Task 15: Logging — Rich progress + verbose/debug lines

**Files:**
- Modify: the orchestration site from Task 14 (the `get_or_fetch_many` call site).
- Modify: `festival_organizer/tracklists/dj_cache.py` if a logger isn't already bound.

**Step 1: Write the failing test**

```python
# tests/test_enrichment_logging.py
import logging


def test_fetch_summary_logged_at_info(caplog):
    """End-of-enrichment INFO line summarises cache hits vs fetches."""
    caplog.set_level(logging.INFO, logger="festival_organizer")
    # Run enrichment against a fixture where N artists are cached and M are new
    # (mock fetcher), then:
    # assert any("Resolved" in r.message and "cached" in r.message for r in caplog.records)


def test_warning_on_fetch_failure(caplog):
    """Slug that fetcher returns None for generates a WARNING."""
    caplog.set_level(logging.WARNING, logger="festival_organizer")
    # Run with a fetcher that returns None for slug "missing"
    # assert any("missing" in r.message and r.levelno == logging.WARNING for r in caplog.records)
```

**Step 2: Run to verify fail**

Run: `pytest tests/test_enrichment_logging.py -v`
Expected: FAIL.

**Step 3: Wire the logging**

At the orchestration site:

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

logger = logging.getLogger(__name__)

slugs_needed = sorted(set(set_owner_slugs) | set(track_slugs))
n_cached = sum(1 for s in slugs_needed if cache.get(s) is not None)
n_missing = len(slugs_needed) - n_cached

if n_missing == 0:
    resolved = cache.get_or_fetch_many(slugs_needed, fetcher=fetcher)
else:
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  console=shared_console) as bar:
        task = bar.add_task("Fetching artist pages", total=n_missing)
        def on_progress(slug, done, total):
            bar.update(task, advance=1, description=f"Fetching artist pages ({slug})")
        resolved = cache.get_or_fetch_many(slugs_needed, fetcher=fetcher,
                                           progress=on_progress)

logger.info("Resolved %d per-track artists (%d cached, %d fetched)",
            len(resolved), n_cached, n_missing)
```

The WARNING for failed fetches already fires inside `get_or_fetch_many` (Task 10). No extra work there.

DEBUG lines for cache lookups and throttle waits already exist in `dj_cache.py` / `api.py`; confirm they're not hidden by the progress context (Rich + logging coexist via the shared Console — consult `.claude/docs/logging.md`).

**Step 4: Run tests + eyeball a real run**

Run: `pytest tests/test_enrichment_logging.py tests/ -x`
Expected: all PASS.

Manual check: run a real enrichment against any small set and watch default / `--verbose` / `--debug` output. Confirm it matches the contract.

**Step 5: Commit**

```bash
git add festival_organizer/metadata.py tests/test_enrichment_logging.py
git commit -m "feat(enrichment): Rich progress and summary logging for artist fetch"
```

---

## Task 16: Config doc — note the jitter behaviour

**Files:**
- Modify: `festival_organizer/config.py` (the `cache_ttl` default section around line 107)

**Step 1: Find the current doc**

Read the comment block around the `cache_ttl` default. It lists `images_days`, `mbid_days`, etc.

**Step 2: Update the doc**

Add a short note (comment or docstring, matching local style) explaining that all values are *base* TTLs and actual per-entry lifetimes spread across ±20% of the base.

No code change. No test.

**Step 3: Commit**

```bash
git add festival_organizer/config.py
git commit -m "docs(config): note ±20% TTL jitter applies to all cache_ttl values"
```

---

## Task 17: End-to-end integration test on the Afrojack EDC 2025 MKV

**Files:**
- Test: `tests/integration/test_afrojack_edc_2025.py` (new; mark `@pytest.mark.integration` and skip unless fixture present)

**Step 1: Write the test**

```python
# tests/integration/test_afrojack_edc_2025.py
"""End-to-end re-enrichment against a known MKV.

Skipped unless /home/martijn/_temp/cratedigger/data/mkv-info-dump contains
the Afrojack EDC 2025 fixture AND 1001TL credentials are available.
"""
import json
import shutil
import subprocess
from pathlib import Path
import pytest

SRC = Path("/home/martijn/_temp/cratedigger/data/mkv-info-dump/"
           "EDC Las Vegas_2025 - Afrojack - EDC Las Vegas [kineticFIELD].json")


@pytest.mark.integration
@pytest.mark.skipif(not SRC.exists(), reason="Afrojack EDC fixture missing")
def test_re_enrichment_produces_canonical_tags_and_per_chapter_tags(tmp_path):
    # 1. Copy the MKV referenced by SRC into tmp_path (read path from SRC json).
    # 2. Run CrateDigger enrichment against the copy.
    # 3. Shell out to mkvmerge -J and parse JSON.
    # 4. Assert: menu["extra"]["CRATEDIGGER_1001TL_ARTISTS"] == "Afrojack"
    # 5. Assert: chapter 0 title starts with "Afrojack" not "AFROJACK"
    # 6. Assert: mkvmerge -J reports chapter tags with ARTIST / GENRE on every
    #    chapter (the exact JSON shape depends on mkvmerge version; inspect
    #    output once, then codify the expected keys).
    # 7. Assert: no chapter title or tag value contains mojibake bytes.
    #    The audit of /home/martijn/_temp/cratedigger/data/mkv-info-dump
    #    found legacy files with Ti├½sto / Am├⌐l / R├£F├£S from before commit
    #    1e45b59. Re-enrichment must produce clean UTF-8.
    #    for s in all_strings: assert "├" not in s, f"mojibake in {s!r}"
    # 8. Assert: ARTIST_SLUGS values use pipe separator (match existing
    #    CRATEDIGGER_1001TL_ARTISTS / _GENRES convention).
```

Add a second test against `Tomorrowland Winter_2026 - Something Else - Tomorrowland Winter.json` to exercise the alias chain (1001TL owner `SOMETHING ELSE` → `artists.json` alias → canonical `ALOK`). Assert both `ARTIST` and `CRATEDIGGER_1001TL_ARTISTS` equal `ALOK` after re-enrichment.

**Step 2: Run it**

Run: `pytest tests/integration/test_afrojack_edc_2025.py -v -m integration`
Expected: PASS (fixture present locally) or SKIP (missing).

If it fails, fix the real code, not the test.

**Step 3: Commit**

```bash
git add tests/integration/test_afrojack_edc_2025.py
git commit -m "test(integration): end-to-end per-chapter tags on Afrojack EDC 2025"
```

---

## Task 18: TrackSplit smoke test

**Files:**
- No CrateDigger source changes.
- Optional: add `tests/integration/test_tracksplit_smoke.py` that shells out to `/home/martijn/TrackSplit/` CLI against the re-enriched MKV from Task 17 and verifies output FLACs carry per-track `ARTIST` and `GENRE`.

**Step 1: Manual smoke**

```bash
# From the re-enriched MKV in the integration test tmp_path:
python /home/martijn/TrackSplit/... <mkv>
# Inspect one of the resulting FLACs:
metaflac --export-tags-to=- <track>.flac | grep -E '^(ARTIST|GENRE)='
```

Expected: per-track `ARTIST` and `GENRE` values populated from the chapter tags, not the global set-level values.

**Step 2: If automatable, codify it**

If TrackSplit has a scriptable mode that exits cleanly on success, wrap the above in a pytest integration test. Otherwise, document the manual verification step in the PR description.

**Step 3: Commit (if a test was added)**

```bash
git add tests/integration/test_tracksplit_smoke.py
git commit -m "test(integration): TrackSplit reads per-chapter tags"
```

---

## Task 19: PR

**Step 1: Confirm the full suite is green**

Run: `pytest tests/ -v`
Expected: every test passes (integration tests may skip).

**Step 2: Push and open the PR**

```bash
git push -u origin feat/per-chapter-tags
gh pr create --title "feat: per-chapter artist/genre tags and unified cache TTL" --body "$(cat <<'EOF'
## Summary
- Parse per-track artist slugs and genres from 1001TL tracklist HTML.
- Emit structured per-chapter tags (TTV=30: ARTIST, ARTIST_SLUGS, GENRE) so TrackSplit can write accurate per-track FLAC tags.
- Unify all artist references through DjCache canonical names (fixes AFROJACK vs Afrojack mismatch).
- Shared jittered-TTL helper applied to all five caches; DJ 30d→90d, Source 30d→365d.
- Version 0.9.8 → 0.9.9.

## Test plan
- [ ] `pytest tests/` passes
- [ ] Integration test against Afrojack EDC 2025 MKV shows canonical CRATEDIGGER_1001TL_ARTISTS and per-chapter tags on mkvmerge -J
- [ ] Manual TrackSplit run produces per-track ARTIST/GENRE on output FLACs
- [ ] Default/verbose/debug logging matches .claude/docs/logging.md contract
EOF
)"
```

---

## Notes

- **Re-enrichment affects existing files.** After this ships, re-run enrichment against the library to pick up canonical names on pre-existing files. The design is additive — existing TTV=50/70 tags only change value (case), not shape, and players that don't read chapter tags are unaffected.
- **Jitter decision record.** The ±20% window is chosen because it spreads 90-day TTLs over ~36 days — enough to fully break any synchronised-expiry wave even after an aggressive first-run bulk fetch — without letting any individual entry live more than ~20% past its nominal freshness budget.
- **DjCache import churn.** Task 14 may touch several callers that currently use `DjCache.get` singly. Don't preemptively migrate them to `get_or_fetch_many`; only the tracklist-enrichment path needs batch resolution. YAGNI.
- **Fixture HTML.** The Afrojack EDC fixture in Task 9 should be committed so CI can run the parser test without 1001TL auth. If the file is large, consider trimming unrelated sections (ads, JS) while preserving the track-row markup.
