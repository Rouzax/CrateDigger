# Chapter Search Improvements

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix chapter search so ALL-CAPS filenames find results and abbreviation-only festivals (AMF) resolve to their full names for better API hits.

**Architecture:** Two independent fixes to the search pipeline: (1) `parse_query()` detects all-caps queries and treats uppercase words as keywords instead of abbreviations, (2) `cli_handler._process_file()` expands known aliases in the search query string before sending to the 1001TL API. Both changes only affect currently-broken code paths — mixed-case queries and filename-based search construction are untouched.

**Tech Stack:** Python 3.12, pytest, no new dependencies

**Background (read before implementing):**
- `scoring.py:parse_query()` splits a search string into keywords (for content matching) and abbreviations (for event matching). The regex `^[A-Z]{2,}$` at line 90 classifies ANY all-uppercase word as an abbreviation. For ALL-CAPS YouTube titles like `"AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026"`, every word becomes an abbreviation, zero keywords are extracted, and the filter at line 155 (`matched_keyword_count == 0`) discards all 30 API results.
- The search query sent to 1001TL's API is the cleaned filename. When that contains abbreviations like "AMF", the API can't find the event — it needs "Amsterdam Music Festival". Expanding aliases in the query fixes this.
- `config.tracklists_aliases` is a `dict[str, str]` mapping lowercase abbreviation → full name (e.g. `{"amf": "Amsterdam Music Festival"}`).
- The `build_search_query()` function and filename parser are NOT modified — they work correctly for all existing cases.

**Verified with real API data:**
```
# ALL-CAPS: 30 raw results → 0 after filter (BROKEN)
Query: "AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026"
  parse_query → keywords=[], abbreviations=[AFROJACK, LIVE, ULTRA, MUSIC, FESTIVAL, MIAMI]

# With fix: 30 raw → 5 scored, correct set at top
  parse_query → keywords=[afrojack, live, ultra, music, festival, miami], abbreviations=[]

# AMF abbreviation: API returns 30 results but no AMF sets (BROKEN)
Query: "Armin van Buuren & KI⧸KI live at AMF 2025 (II=I)"

# With alias expansion: "Amsterdam Music Festival" in query → AMF set is result #2
Query: "Armin van Buuren & KI⧸KI live at Amsterdam Music Festival 2025 (II=I)"
```

---

### Task 1: All-caps-aware `parse_query` — tests

**Files:**
- Modify: `tests/test_tracklists_scoring.py`

**Step 1: Write failing tests for all-caps query parsing**

Add these tests after the existing `test_parse_query_no_short_words` test (line 78):

```python
def test_parse_query_all_caps_produces_keywords():
    """ALL-CAPS queries (YouTube titles) should produce keywords, not just abbreviations."""
    aliases = {"umf": "Ultra Music Festival"}
    parts = parse_query("AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026", aliases)
    assert parts.year == "2026"
    # All-caps words should become keywords, not abbreviations
    assert "afrojack" in parts.keywords
    assert "live" in parts.keywords
    assert "ultra" in parts.keywords
    assert "festival" in parts.keywords
    assert "miami" in parts.keywords
    # Should NOT have spurious abbreviations from regular words
    assert "AFROJACK" not in parts.abbreviations
    assert "FESTIVAL" not in parts.abbreviations


def test_parse_query_all_caps_preserves_known_alias():
    """ALL-CAPS queries should still detect known alias abbreviations."""
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("AMF AFROJACK 2025", aliases)
    assert parts.year == "2025"
    # AMF is a known alias — should be abbreviation AND keyword
    assert "AMF" in parts.abbreviations
    assert len(parts.resolved_aliases) == 1
    assert parts.resolved_aliases[0]["target"] == "Amsterdam Music Festival"
    # AFROJACK is not a known alias — should be keyword only
    assert "afrojack" in parts.keywords
    assert "AFROJACK" not in parts.abbreviations


def test_parse_query_mixed_case_unchanged():
    """Mixed-case queries preserve existing abbreviation behavior."""
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("2025 AMF Sub Zero Project", aliases)
    # AMF → abbreviation (existing behavior)
    assert "AMF" in parts.abbreviations
    # Sub, Zero, Project → keywords (existing behavior)
    assert "sub" in parts.keywords
    assert "zero" in parts.keywords
    assert "project" in parts.keywords
    # Keywords should NOT include "amf" (mixed-case: abbreviations stay separate)
    assert "amf" not in parts.keywords
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tracklists_scoring.py::test_parse_query_all_caps_produces_keywords tests/test_tracklists_scoring.py::test_parse_query_all_caps_preserves_known_alias tests/test_tracklists_scoring.py::test_parse_query_mixed_case_unchanged -v`

Expected: First two FAIL (keywords empty, abbreviations populated). Third should PASS (existing behavior).

**Step 3: Commit test stubs**

```bash
git add tests/test_tracklists_scoring.py
git commit -m "test: add failing tests for all-caps query keyword extraction"
```

---

### Task 2: All-caps-aware `parse_query` — implementation

**Files:**
- Modify: `festival_organizer/tracklists/scoring.py:54-111`

**Step 1: Implement all-caps detection and conditional abbreviation handling**

In `parse_query()`, replace lines 69–111 (from `words = query.split()` through the end of the function) with:

```python
    words = query.split()
    remaining = []

    # Detect all-caps query (YouTube title convention)
    alpha_words = [w for w in words if re.match(r"^[A-Za-z]{2,}$", w)]
    all_caps_query = len(alpha_words) > 1 and all(w.isupper() for w in alpha_words)

    for word in words:
        # Year detection
        if re.match(r"^(19|20)\d{2}$", word):
            parts.year = word
            continue

        # Event patterns: WE1, W2, Weekend1, D1, Day2
        we_match = re.match(r"(?i)^(?:WE|W|Weekend)(\d+)$", word)
        if we_match:
            parts.event_patterns.append({"type": "Weekend", "number": we_match.group(1)})
            continue

        day_match = re.match(r"(?i)^(?:D|Day)(\d+)$", word)
        if day_match:
            parts.event_patterns.append({"type": "Day", "number": day_match.group(1)})
            continue

        # Abbreviation detection: exactly 2+ uppercase letters, no lowercase
        if re.match(r"^[A-Z]{2,}$", word):
            lower = word.lower()
            is_known_alias = lower in aliases

            if all_caps_query:
                # All-caps query: only known aliases are treated as abbreviations
                if is_known_alias:
                    parts.abbreviations.append(word)
                    parts.resolved_aliases.append({"alias": word, "target": aliases[lower]})
                # Always also a keyword candidate in all-caps mode
                remaining.append(word)
                continue
            else:
                # Mixed-case query: existing behavior — all uppercase words are abbreviations
                parts.abbreviations.append(word)
                if is_known_alias:
                    parts.resolved_aliases.append({"alias": word, "target": aliases[lower]})
                continue

        # Alias check (case-insensitive)
        lower = word.lower()
        if lower in aliases:
            parts.resolved_aliases.append({"alias": word, "target": aliases[lower]})

        remaining.append(word)

    # Keywords: words > 2 chars, lowercased, with diacritics removed
    for word in remaining:
        cleaned = remove_diacritics(word).lower()
        if len(cleaned) > 2:
            parts.keywords.append(cleaned)

    return parts
```

**Step 2: Run all scoring tests**

Run: `python -m pytest tests/test_tracklists_scoring.py -v`

Expected: ALL tests pass — the three new ones plus all existing tests. Especially verify:
- `test_parse_query_basic` — still passes (mixed-case, AMF is abbreviation)
- `test_parse_query_no_short_words` — still passes ("DJ at an AMF" is mixed-case due to "at"/"an")
- `test_parse_query_all_caps_produces_keywords` — now passes
- `test_parse_query_all_caps_preserves_known_alias` — now passes

**Step 3: Commit**

```bash
git add festival_organizer/tracklists/scoring.py
git commit -m "fix: all-caps queries extract keywords instead of only abbreviations

YouTube titles are often ALL-CAPS (e.g. 'AFROJACK LIVE @ ULTRA MUSIC
FESTIVAL MIAMI 2026'). Previously, every uppercase word was classified
as an abbreviation, leaving zero keywords and causing all search results
to be filtered out. Now detects all-caps queries and treats words as
keywords, only classifying known aliases as abbreviations."
```

---

### Task 3: Alias expansion in search query — tests

**Files:**
- Modify: `tests/test_tracklists_query.py`

**Step 1: Write failing tests for alias expansion**

Add at the end of the file:

```python
from festival_organizer.tracklists.query import expand_aliases_in_query


def test_expand_aliases_replaces_abbreviation():
    aliases = {"amf": "Amsterdam Music Festival"}
    result = expand_aliases_in_query("Armin van Buuren live at AMF 2025", aliases)
    assert "Amsterdam Music Festival" in result
    assert "AMF" not in result


def test_expand_aliases_case_insensitive():
    aliases = {"edc": "Electric Daisy Carnival"}
    result = expand_aliases_in_query("Tiesto EDC Las Vegas", aliases)
    assert "Electric Daisy Carnival" in result


def test_expand_aliases_no_match_unchanged():
    aliases = {"amf": "Amsterdam Music Festival"}
    result = expand_aliases_in_query("Hardwell Tomorrowland 2025", aliases)
    assert result == "Hardwell Tomorrowland 2025"


def test_expand_aliases_word_boundary():
    """Should not replace partial word matches."""
    aliases = {"ed": "Something"}
    result = expand_aliases_in_query("Red Rocks 2025", aliases)
    assert result == "Red Rocks 2025"  # "ed" in "Red" should NOT match
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tracklists_query.py::test_expand_aliases_replaces_abbreviation -v`

Expected: FAIL with `ImportError: cannot import name 'expand_aliases_in_query'`

**Step 3: Commit**

```bash
git add tests/test_tracklists_query.py
git commit -m "test: add failing tests for alias expansion in search queries"
```

---

### Task 4: Alias expansion in search query — implementation

**Files:**
- Modify: `festival_organizer/tracklists/query.py:1-28`
- Modify: `festival_organizer/tracklists/cli_handler.py:184-198`

**Step 1: Add `expand_aliases_in_query` to query.py**

Add this function after the existing `build_search_query` function (after line 28):

```python
def expand_aliases_in_query(query: str, aliases: dict[str, str]) -> str:
    """Expand known abbreviations in a query string to their full names.

    Args:
        query: search query string
        aliases: lowercase-keyed alias map (e.g. {"amf": "Amsterdam Music Festival"})

    Returns:
        Query with abbreviations replaced by full names.
    """
    for abbrev, full_name in aliases.items():
        query = re.sub(rf"\b{re.escape(abbrev)}\b", full_name, query, flags=re.IGNORECASE)
    return query
```

**Step 2: Run the query tests**

Run: `python -m pytest tests/test_tracklists_query.py -v`

Expected: ALL tests pass (existing + new).

**Step 3: Wire alias expansion into the search flow in cli_handler.py**

In `_process_file()`, add the import at the top of the file (with the existing query imports around line 27):

```python
from festival_organizer.tracklists.query import (
    build_search_query,
    detect_tracklist_source,
    extract_tracklist_id,
    expand_aliases_in_query,
)
```

Then in `_process_file()`, insert alias expansion between lines 185 and 186 (after `query_str = source["value"]`, before the `if not quiet:` print):

```python
    # Search
    query_str = source["value"]

    # Expand known abbreviations for better API results (AMF → Amsterdam Music Festival)
    aliases = config.tracklists_aliases
    query_str = expand_aliases_in_query(query_str, aliases)

    if not quiet:
        print(f"  Searching: {query_str}")
```

And update the later alias reference (around line 196) to reuse the same variable. Change:

```python
    # Score results
    aliases = config.tracklists_aliases
    query_parts = parse_query(query_str, aliases)
```

To:

```python
    # Score results (aliases already loaded above)
    query_parts = parse_query(query_str, aliases)
```

**Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: ALL tests pass.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/query.py festival_organizer/tracklists/cli_handler.py
git commit -m "fix: expand aliases in search query before sending to 1001TL API

Abbreviations like 'AMF' in filenames don't match 1001TL's search index.
Now expands known aliases (AMF → Amsterdam Music Festival) in the query
string before the API call, so the search finds the actual event."
```

---

### Task 5: Unicode slash normalization in search query

**Files:**
- Modify: `festival_organizer/tracklists/query.py:1-28`
- Modify: `tests/test_tracklists_query.py`

**Step 1: Write failing test**

Add to `tests/test_tracklists_query.py`:

```python
def test_build_search_query_normalizes_unicode_slashes():
    """Unicode fraction slashes (KI⧸KI) should become spaces."""
    result = build_search_query(Path("Armin van Buuren & KI⧸KI live at AMF 2025 [WownWX6HUTs].mkv"))
    assert "⧸" not in result
    assert "KI" in result
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tracklists_query.py::test_build_search_query_normalizes_unicode_slashes -v`

Expected: FAIL — `⧸` is still in the result.

**Step 3: Add unicode normalization to `build_search_query`**

In `query.py`, update the import line and add one line after the YouTube ID strip:

```python
from festival_organizer.normalization import extract_youtube_id, strip_scene_tags, strip_noise_words, UNICODE_SLASHES
```

In `build_search_query`, add after `stem, _ = extract_youtube_id(stem)` (after line 16):

```python
    # Normalize unicode slashes (KI⧸KI → KI KI)
    stem = UNICODE_SLASHES.sub(" ", stem)
```

**Step 4: Run all query tests**

Run: `python -m pytest tests/test_tracklists_query.py -v`

Expected: ALL pass.

**Step 5: Commit**

```bash
git add festival_organizer/tracklists/query.py tests/test_tracklists_query.py
git commit -m "fix: normalize unicode slashes in search queries

Characters like ⧸ (U+29F8) in filenames like 'KI⧸KI' pollute search
queries. Now normalizes to spaces using existing UNICODE_SLASHES regex."
```

---

### Task 6: Source cache `derive_aliases` — tests and implementation

**Files:**
- Modify: `festival_organizer/tracklists/source_cache.py`
- Create: `tests/test_tracklists_source_cache.py`

**Step 1: Write tests**

Create `tests/test_tracklists_source_cache.py`:

```python
"""Tests for source cache alias derivation."""
import json
import pytest
from pathlib import Path
from festival_organizer.tracklists.source_cache import SourceCache


@pytest.fixture
def cache_with_sources(tmp_path):
    """Source cache pre-loaded with festival and venue entries."""
    cache_path = tmp_path / "source_cache.json"
    data = {
        "5tb5n3": {"name": "Amsterdam Music Festival", "slug": "amsterdam-music-festival", "type": "Open Air / Festival", "country": "Netherlands"},
        "u8bf5c": {"name": "Ultra Music Festival Miami", "slug": "ultra-music-festival-miami", "type": "Open Air / Festival", "country": "United States"},
        "hdfr2c": {"name": "Johan Cruijff ArenA", "slug": "johan-cruijff-arena-amsterdam", "type": "Event Location", "country": "Netherlands"},
        "f4lzj3": {"name": "Amsterdam Dance Event", "slug": "amsterdam-dance-event", "type": "Conference", "country": "Netherlands"},
        "m3b0d3": {"name": "A State Of Trance", "slug": "a-state-of-trance", "type": "Radio Channel", "country": ""},
        "fgcfkm": {"name": "Tomorrowland", "slug": "tomorrowland", "type": "Open Air / Festival", "country": "Belgium"},
    }
    cache_path.write_text(json.dumps(data))
    return SourceCache(cache_path=cache_path)


def test_derive_aliases_festivals(cache_with_sources):
    aliases = cache_with_sources.derive_aliases()
    assert aliases["amf"] == "Amsterdam Music Festival"
    assert aliases["umfm"] == "Ultra Music Festival Miami"


def test_derive_aliases_includes_conferences(cache_with_sources):
    aliases = cache_with_sources.derive_aliases()
    assert aliases["ade"] == "Amsterdam Dance Event"


def test_derive_aliases_excludes_venues(cache_with_sources):
    """Event Location (venues) should not produce aliases."""
    aliases = cache_with_sources.derive_aliases()
    assert "jca" not in aliases  # Johan Cruijff ArenA


def test_derive_aliases_excludes_radio(cache_with_sources):
    aliases = cache_with_sources.derive_aliases()
    assert "asot" not in aliases  # A State Of Trance — radio, not festival


def test_derive_aliases_skips_single_word(cache_with_sources):
    """Single-word festival names don't produce abbreviations."""
    aliases = cache_with_sources.derive_aliases()
    assert "t" not in aliases  # Tomorrowland has no multi-word abbreviation


def test_derive_aliases_empty_cache(tmp_path):
    cache_path = tmp_path / "source_cache.json"
    cache = SourceCache(cache_path=cache_path)
    assert cache.derive_aliases() == {}
```

**Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_tracklists_source_cache.py -v`

Expected: FAIL with `AttributeError: 'SourceCache' object has no attribute 'derive_aliases'`

**Step 3: Implement `derive_aliases` on SourceCache**

Add this import at the top of `source_cache.py` (after existing imports):

```python
from festival_organizer.tracklists.scoring import get_abbreviation
```

Add this method to the `SourceCache` class (after the `group_by_type` method):

```python
    def derive_aliases(self) -> dict[str, str]:
        """Derive abbreviation → full name map from cached festival/event sources.

        Inspects cached sources of type "Open Air / Festival" and "Conference",
        derives abbreviations from multi-word names using first-letter extraction.
        Returns lowercase-keyed dict matching the format of config.tracklists_aliases.
        """
        aliases: dict[str, str] = {}
        for entry in self._data.values():
            if entry.get("type") not in ("Open Air / Festival", "Conference"):
                continue
            name = entry.get("name", "")
            abbrev = get_abbreviation(name)
            if abbrev and len(abbrev) >= 2:
                aliases[abbrev.lower()] = name
        return aliases
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_tracklists_source_cache.py -v`

Expected: ALL pass.

**Step 5: Wire derived aliases into the search flow**

In `cli_handler.py`, in `_process_file()`, update the alias loading to merge source cache aliases. Find the line (from Task 4):

```python
    aliases = config.tracklists_aliases
```

Replace with:

```python
    aliases = {**source_cache.derive_aliases(), **config.tracklists_aliases}
```

This requires `source_cache` to be accessible in `_process_file`. It's already available in the outer `run_chapters()` function. Thread it through by adding `source_cache` to the `_process_file` signature and call site.

In `_process_file` signature (line 124), add `source_cache` parameter:

```python
def _process_file(
    filepath: Path,
    scan_root: Path,
    session: TracklistSession,
    config: Config,
    source_cache: "SourceCache",
    tracklist_input: str | None,
    ...
```

In `run_chapters()` call site (line 93), add `source_cache`:

```python
            status = _process_file(
                filepath=filepath,
                scan_root=scan_root,
                session=session,
                config=config,
                source_cache=source_cache,
                tracklist_input=tracklist_input,
                ...
```

**Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: ALL pass.

**Step 7: Commit**

```bash
git add festival_organizer/tracklists/source_cache.py festival_organizer/tracklists/cli_handler.py tests/test_tracklists_source_cache.py
git commit -m "feat: derive aliases from source cache for smarter abbreviation expansion

The source cache accumulates festival/venue names from previously
processed tracklists. Now derives abbreviations (AMF, UMF, etc.) from
cached multi-word festival names and merges them with static config
aliases. This makes the system self-learning: as more files are
processed and the cache grows, future searches auto-resolve more
abbreviations."
```

---

### Task 7: End-to-end scoring verification

**Files:**
- Modify: `tests/test_tracklists_scoring.py`

**Step 1: Add end-to-end test for ALL-CAPS search + score pipeline**

Add at the end of the scoring test file:

```python
def test_all_caps_query_scores_matching_results():
    """ALL-CAPS query should score and return matching results, not filter all out."""
    results = [
        SearchResult(id="1", title="AFROJACK @ Mainstage, Ultra Music Festival Miami, United States", url="", duration_mins=60, date="2026-03-29"),
        SearchResult(id="2", title="ZHU @ Live Stage, Ultra Music Festival Miami, United States", url="", duration_mins=58, date="2026-03-29"),
        SearchResult(id="3", title="Random DJ - Radio Show 123", url="", duration_mins=60, date="2026-01-01"),
    ]
    aliases = {"umf": "Ultra Music Festival"}
    parts = parse_query("AFROJACK LIVE @ ULTRA MUSIC FESTIVAL MIAMI 2026", aliases)
    scored = score_results(results, parts, video_duration_minutes=60)
    # Should NOT filter everything out
    assert len(scored) >= 2
    # AFROJACK result should score highest (matches artist + festival keywords)
    assert scored[0].id == "1"


def test_mixed_case_with_alias_still_filters_correctly():
    """Regression: mixed-case queries with aliases should keep strict filtering."""
    results = [
        SearchResult(id="1", title="Sub Zero Project @ Amsterdam Music Festival 2025", url=""),
        SearchResult(id="2", title="Sub Random Other Track 2025", url=""),
    ]
    aliases = {"amf": "Amsterdam Music Festival"}
    parts = parse_query("2025 AMF Sub Zero Project", aliases)
    scored = score_results(results, parts)
    # Result 1 should be present and highly scored
    assert any(r.id == "1" for r in scored)
    # Result 2 should be filtered or score much lower (only 1 keyword match "sub", no event)
    if any(r.id == "2" for r in scored):
        r1_score = next(r.score for r in scored if r.id == "1")
        r2_score = next(r.score for r in scored if r.id == "2")
        assert r1_score > r2_score
```

**Step 2: Run all scoring tests**

Run: `python -m pytest tests/test_tracklists_scoring.py -v`

Expected: ALL pass.

**Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: ALL pass.

**Step 4: Commit**

```bash
git add tests/test_tracklists_scoring.py
git commit -m "test: add end-to-end scoring tests for all-caps and mixed-case queries"
```
