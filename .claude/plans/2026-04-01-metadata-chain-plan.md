# Clean Metadata Chain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace lossy title string parsing with dedicated structured tags for all metadata fields, add DJ profile scraping for artist aliases/groups, and promote unmapped source types so every file gets a festival tag.

**Architecture:** Extend the existing `<h1>` parser to also extract DJ links (artist data). Add a `DjCache` that stores artist aliases and group memberships from DJ profile pages. Add promotion logic so "Concert / Live Event" and "Event Promoter" sources become festival tags when no "Open Air / Festival" source exists. Remove `parse_1001tracklists_title()` entirely since all its outputs are now covered by dedicated tags.

**Tech Stack:** Python 3.12, pytest, requests (existing 1001TL session), JSON file caches

**Design doc:** `docs/plans/2026-04-01-metadata-chain-design.md`

---

### Task 1: Extract DJ artists from `<h1>` structure

**Files:**
- Modify: `festival_organizer/tracklists/api.py:413-443` (`_parse_h1_structure`)
- Modify: `festival_organizer/tracklists/api.py:38-47` (`TracklistExport` dataclass)
- Modify: `festival_organizer/tracklists/api.py:168-204` (`export_tracklist` method)
- Test: `tests/test_tracklists_api.py` (or `tests/test_h1_parser.py`, whichever exists)

**Context:** The `<h1>` on a 1001TL tracklist page has `/dj/` links before the `@` for each artist. Currently `_parse_h1_structure` only parses after the `@`. We need to also extract the before-`@` DJ links.

Example h1 HTML:
```html
<a href="/dj/arminvanbuuren/index.html">Armin van Buuren</a> &
<a href="/dj/kislashki/index.html">KI/KI</a> @ Two Is One,
<a href="/source/5tb5n3/amsterdam-music-festival/index.html">Amsterdam Music Festival</a>
```

**Step 1: Write failing tests**

Add tests for `_parse_h1_structure` that verify DJ link extraction:

```python
def test_h1_extracts_single_dj():
    h1 = '<a href="/dj/tiesto/index.html" class="notranslate ">Tiësto</a> @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a>'
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("tiesto", "Tiësto")]
    assert result["stage_text"] == "Mainstage"

def test_h1_extracts_collab_djs():
    h1 = '<a href="/dj/arminvanbuuren/index.html" class="notranslate ">Armin van Buuren</a> & <a href="/dj/kislashki/index.html" class="notranslate ">KI/KI</a> @ Two Is One, <a href="/source/5tb5n3/amsterdam-music-festival/index.html">Amsterdam Music Festival</a>'
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("arminvanbuuren", "Armin van Buuren"), ("kislashki", "KI/KI")]
    assert result["stage_text"] == "Two Is One"

def test_h1_extracts_group_dj():
    h1 = '<a href="/dj/dimitrivegasandlikemike/index.html" class="notranslate ">Dimitri Vegas &amp; Like Mike</a> @ Mainstage, <a href="/source/fgcfkm/tomorrowland/index.html">Tomorrowland</a> Weekend 2, Belgium 2025-07-26'
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == [("dimitrivegasandlikemike", "Dimitri Vegas & Like Mike")]

def test_h1_no_at_sign():
    h1 = "Mysteryland - Aftermovie 2025-09-15"
    result = _parse_h1_structure(h1)
    assert result["dj_artists"] == []
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_h1_parser.py -v` (or wherever the tests live)
Expected: FAIL with `KeyError: 'dj_artists'`

**Step 3: Implement DJ extraction in `_parse_h1_structure`**

In `api.py:413-443`, extend the function:
- Add `"dj_artists": []` to the result dict
- Parse before-`@` part with pattern: `r'<a[^>]*href="/dj/([^/"]+)/[^"]*"[^>]*>([^<]+)</a>'`
- HTML-decode each display name
- Return as list of `(slug, display_name)` tuples

**Step 4: Add `dj_artists` to `TracklistExport`**

In `api.py:38-47`, add field:
```python
dj_artists: list[tuple[str, str]] = field(default_factory=list)
```

In `api.py:168-204` (`export_tracklist`), pass `dj_artists` from `h1_info` to the export. Also replace the `_extract_dj_slugs()` call for artwork with the h1 DJ slugs (more precise, scoped to actual artists instead of all page links).

**Step 5: Run tests to verify they pass**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 6: Commit**

```
feat(tracklists): extract DJ artist links from h1 structure
```

---

### Task 2: Create DJ cache with profile scraping

**Files:**
- Create: `festival_organizer/tracklists/dj_cache.py`
- Modify: `festival_organizer/tracklists/api.py:324-337` (`_fetch_dj_artwork` becomes `_fetch_dj_profile`)
- Test: `tests/test_dj_cache.py`

**Context:** DJ profile pages at `/dj/<slug>/` have structured sections for "Aliases" and "Member Of", each containing `/dj/` links. We already visit these pages for artwork. We should extract profile data from the same request.

Example page structure (cleaned):
```
Aliases: <a href="/dj/verwest/">VER:WEST</a>, <a href="/dj/allurenl/">Allure</a>
Member Of: <a href="/dj/gaia-nl/">Gaia</a>
```

**Step 1: Write failing tests for DjCache**

```python
def test_dj_cache_put_get(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("tiesto", {
        "name": "Tiësto",
        "artwork_url": "https://example.com/tiesto.jpg",
        "aliases": [{"slug": "verwest", "name": "VER:WEST"}],
        "member_of": [],
    })
    entry = cache.get("tiesto")
    assert entry["name"] == "Tiësto"
    assert entry["aliases"][0]["name"] == "VER:WEST"

def test_dj_cache_derive_aliases(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("tiesto", {
        "name": "Tiësto",
        "artwork_url": "",
        "aliases": [{"slug": "verwest", "name": "VER:WEST"}, {"slug": "allurenl", "name": "Allure"}],
        "member_of": [],
    })
    aliases = cache.derive_artist_aliases()
    assert aliases["VER:WEST"] == "Tiësto"
    assert aliases["Allure"] == "Tiësto"

def test_dj_cache_derive_groups(tmp_path):
    cache = DjCache(tmp_path / "dj_cache.json")
    cache.put("arminvanbuuren", {
        "name": "Armin van Buuren",
        "artwork_url": "",
        "aliases": [],
        "member_of": [{"slug": "gaia-nl", "name": "Gaia"}],
    })
    groups = cache.derive_artist_groups()
    assert "gaia" in groups
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dj_cache.py -v`
Expected: FAIL with `ImportError`

**Step 3: Implement `DjCache`**

Create `festival_organizer/tracklists/dj_cache.py`. Model after `SourceCache` in `source_cache.py`:
- Same JSON persistence pattern
- `DEFAULT_PATH = Path.home() / ".cratedigger" / "dj_cache.json"`
- `get(slug)`, `put(slug, entry)` methods
- `derive_artist_aliases()`: returns `{alias_name: canonical_name}` for all cached DJs
- `derive_artist_groups()`: returns `set[str]` of lowercased group names from `member_of` entries

**Step 4: Write tests for DJ profile parsing**

```python
def test_parse_dj_profile_with_aliases():
    html = '...Aliases...VER:WEST...</a>...<a href="/dj/allurenl/index.html">Allure</a>...'
    result = _parse_dj_profile(html)
    assert result["aliases"] == [{"slug": "verwest", "name": "VER:WEST"}, {"slug": "allurenl", "name": "Allure"}]

def test_parse_dj_profile_with_member_of():
    html = '...Member Of...<a href="/dj/gaia-nl/index.html">Gaia</a>...'
    result = _parse_dj_profile(html)
    assert result["member_of"] == [{"slug": "gaia-nl", "name": "Gaia"}]
```

Use real HTML snippets from the pages we already fetched during investigation for accurate test data.

**Step 5: Implement `_parse_dj_profile` and refactor `_fetch_dj_artwork`**

In `api.py`, rename `_fetch_dj_artwork` to `_fetch_dj_profile`. It already fetches the DJ page. Extend it to:
1. Extract `og:image` (artwork, existing logic)
2. Parse "Aliases" section for `/dj/` links
3. Parse "Member Of" section for `/dj/` links
4. Return a dict: `{"artwork_url": str, "aliases": [...], "member_of": [...]}`

The section parsing approach: find the section header text ("Aliases", "Member Of", "Group Members"), then extract `/dj/` links between that header and the next section header (or end of the info block).

In `export_tracklist`, call `_fetch_dj_profile` for each DJ slug from the h1, store results in DjCache. Use the first DJ's artwork_url as `dj_artwork_url` (preserves existing behavior).

**Step 6: Run all tests**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 7: Commit**

```
feat(tracklists): add DJ cache with alias and group scraping from profiles
```

---

### Task 3: Promote unmapped source types to festival

**Files:**
- Modify: `festival_organizer/tracklists/source_cache.py:80-87` (`group_by_type`)
- Test: `tests/test_source_cache.py` (or inline in existing test file)

**Context:** When `sources_by_type` has no "Open Air / Festival", we should promote the first "Concert / Live Event" or "Event Promoter" source into that slot. This ensures every event gets a `CRATEDIGGER_1001TL_FESTIVAL` tag.

**Step 1: Write failing tests**

```python
def test_promote_concert_to_festival(tmp_path):
    cache = SourceCache(tmp_path / "sc.json")
    cache.put("rch80m", {"name": "A State Of Trance Festival", "slug": "asot", "type": "Concert / Live Event", "country": "Netherlands"})
    cache.put("tslp1m", {"name": "Ahoy Rotterdam", "slug": "ahoy", "type": "Event Location", "country": "Netherlands"})
    groups = cache.group_by_type(["rch80m", "tslp1m"])
    assert "Open Air / Festival" in groups
    assert "A State Of Trance Festival" in groups["Open Air / Festival"]

def test_promote_event_promoter_to_festival(tmp_path):
    cache = SourceCache(tmp_path / "sc.json")
    cache.put("5j4wgtv", {"name": "We Belong Here", "slug": "wbh", "type": "Event Promoter", "country": "United States"})
    cache.put("7xp1dkc", {"name": "Historic Virginia Key Park", "slug": "hvkp", "type": "Event Location", "country": "United States"})
    groups = cache.group_by_type(["5j4wgtv", "7xp1dkc"])
    assert "Open Air / Festival" in groups
    assert "We Belong Here" in groups["Open Air / Festival"]

def test_no_promotion_when_festival_exists(tmp_path):
    cache = SourceCache(tmp_path / "sc.json")
    cache.put("u8bf5c", {"name": "Ultra Music Festival Miami", "slug": "umf", "type": "Open Air / Festival", "country": "United States"})
    cache.put("v088zc", {"name": "Resistance", "slug": "resistance", "type": "Event Promoter", "country": "Worldwide"})
    groups = cache.group_by_type(["u8bf5c", "v088zc"])
    assert groups["Open Air / Festival"] == ["Ultra Music Festival Miami"]
    assert "Event Promoter" in groups
    assert "Resistance" in groups["Event Promoter"]

def test_concert_promoted_before_event_promoter(tmp_path):
    """If both Concert/Live Event and Event Promoter present, Concert wins."""
    cache = SourceCache(tmp_path / "sc.json")
    cache.put("aaa", {"name": "Some Concert", "slug": "sc", "type": "Concert / Live Event", "country": "NL"})
    cache.put("bbb", {"name": "Some Promoter", "slug": "sp", "type": "Event Promoter", "country": "NL"})
    groups = cache.group_by_type(["aaa", "bbb"])
    assert groups["Open Air / Festival"] == ["Some Concert"]
```

**Step 2: Run tests to verify they fail**

Expected: FAIL because `group_by_type` doesn't promote yet.

**Step 3: Implement promotion in `group_by_type`**

In `source_cache.py:80-87`, after building the groups dict, add promotion logic:

```python
def group_by_type(self, source_ids: list[str]) -> dict[str, list[str]]:
    """Group source names by their type. Returns {type: [name, ...]}."""
    groups: dict[str, list[str]] = {}
    for sid in source_ids:
        entry = self._data.get(sid)
        if entry:
            groups.setdefault(entry["type"], []).append(entry["name"])

    # Promote unmapped types to festival when no festival exists
    if "Open Air / Festival" not in groups:
        for fallback_type in ("Concert / Live Event", "Event Promoter"):
            if fallback_type in groups:
                groups["Open Air / Festival"] = groups.pop(fallback_type)
                break

    return groups
```

**Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 5: Commit**

```
feat(tracklists): promote Concert/Live Event and Event Promoter to festival
```

---

### Task 4: Write `CRATEDIGGER_1001TL_ARTISTS` tag in chapters command

**Files:**
- Modify: `festival_organizer/tracklists/chapters.py:239-303` (`embed_chapters`)
- Modify: `festival_organizer/tracklists/chapters.py:167-214` (`extract_stored_tracklist_info`)
- Modify: `festival_organizer/tracklists/cli_handler.py:312-325` (tag building)
- Test: existing chapter tests

**Context:** The chapters command needs to write a new `CRATEDIGGER_1001TL_ARTISTS` tag from the DJ artist names extracted from the `<h1>`. Pipe-separated, like genres.

**Step 1: Add `dj_artists` parameter to `embed_chapters`**

In `chapters.py:239-249`, add parameter `dj_artists: list[tuple[str, str]] | None = None`.

In the tag building block (line 284-302), add:
```python
if dj_artists:
    tags["CRATEDIGGER_1001TL_ARTISTS"] = "|".join(name for _, name in dj_artists)
```

**Step 2: Add to `extract_stored_tracklist_info` tag_map**

In `chapters.py:176-196`, add to the tag_map:
```python
"CRATEDIGGER_1001TL_ARTISTS": "artists",
```

**Step 3: Update `cli_handler.py` tag building**

In `cli_handler.py:312-325`, add the artists tag to the `desired` dict:
```python
if export.dj_artists:
    desired["CRATEDIGGER_1001TL_ARTISTS"] = "|".join(name for _, name in export.dj_artists)
```

Also add to the `stored_map` on line 326-337:
```python
"CRATEDIGGER_1001TL_ARTISTS": stored.get("artists", ""),
```

In the `embed_chapters` calls on lines 291, 302, 373, pass `dj_artists=export.dj_artists`.

**Step 4: Run tests**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 5: Commit**

```
feat(tracklists): write CRATEDIGGER_1001TL_ARTISTS tag in chapters command
```

---

### Task 5: Read artists tag in metadata extraction

**Files:**
- Modify: `festival_organizer/metadata.py:112-160`
- Test: existing metadata tests

**Step 1: Add `tracklists_artists` to metadata extraction**

In `metadata.py`, add to the return dict (near line 157):
```python
"tracklists_artists": (
    general.get("CRATEDIGGER_1001TL_ARTISTS", "")
    or extra.get("CRATEDIGGER_1001TL_ARTISTS", "")
),
```

Also add to the ffprobe fallback path (near line 237) if it exists.

**Step 2: Run tests**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 3: Commit**

```
feat(metadata): read CRATEDIGGER_1001TL_ARTISTS tag
```

---

### Task 6: Rewrite analyzer to use dedicated tags, remove title parser

**Files:**
- Modify: `festival_organizer/analyzer.py` (entire file)
- Modify: `festival_organizer/parsers.py:30-127` (remove `parse_1001tracklists_title`)
- Modify: `festival_organizer/config.py:327-338` (merge DJ cache aliases/groups)
- Modify: `tests/test_parsers.py:14-102` (remove title parser tests)
- Test: `tests/test_analyzer.py`

**Context:** This is the core change. The analyzer currently has 5 layers. Layer 4 (title parser) is removed. The new `tracklists_artists` tag replaces the title parser's artist extraction. The `display_artist` logic simplifies because we now have pipe-separated artist names.

**Step 1: Remove `parse_1001tracklists_title` from parsers.py**

Delete lines 30-127 in `parsers.py` (the entire function).

Remove from the import in `parsers.py`'s public API if it has `__all__`.

**Step 2: Remove title parser tests**

Delete `test_1001tl_basic_festival` through `test_1001tl_empty` in `tests/test_parsers.py` (lines 14-102). Keep all filename parser tests.

Update the import at the top of `test_parsers.py` to remove `parse_1001tracklists_title`.

**Step 3: Rewrite analyzer.py**

Remove the import of `parse_1001tracklists_title` (line 20).

Remove the call on lines 41-43.

Remove Layer 4 (lines 86-98) which sets fields from `tracklists_info`.

Replace the `display_artist` building (lines 117-134) with:

```python
# Build artist and display_artist from 1001TL artists tag (highest priority)
tracklists_artists_raw = meta.get("tracklists_artists", "")
if tracklists_artists_raw:
    artists_list = [a.strip() for a in tracklists_artists_raw.split("|") if a.strip()]
    if artists_list:
        # 1 entry = solo or group (use as-is)
        # 2+ entries = collab (first = primary, joined = display)
        info["artist"] = artists_list[0]
        if len(artists_list) > 1:
            display_artist = " & ".join(artists_list)
        else:
            display_artist = artists_list[0]
        metadata_source = "1001tracklists"
```

Keep existing display_artist fallback logic for files without 1001TL data (parent dir, filename).

Keep the Layer 5 festival tag resolution as-is (lines 103-115).

Keep the `tracklists_stage` and `tracklists_venue` direct tag reads (lines 99-102).

Update the `metadata_source` logic to account for the removed Layer 4.

**Step 4: Merge DJ cache data into config**

In `config.py`, modify `artist_aliases` property (line 327-331) and `artist_groups` property (line 334-338) to also load from DJ cache:

```python
@property
def artist_aliases(self) -> dict[str, str]:
    raw = self._load_external_config("artists.json", {}).get("aliases", {})
    if "artist_aliases" in self._data:
        raw = {**raw, **self._data["artist_aliases"]}
    flat = _invert_alias_map(raw)
    # Merge DJ cache aliases (lower priority than manual config)
    dj_aliases = self._load_dj_aliases()
    return {**dj_aliases, **flat}  # manual overrides DJ cache

@property
def artist_groups(self) -> set[str]:
    if "artist_groups" in self._data:
        groups = {g.lower() for g in self._data["artist_groups"]}
    else:
        groups = set()
    ext_groups = self._load_external_config("artists.json", {}).get("groups", [])
    groups.update(g.lower() for g in ext_groups)
    # Merge DJ cache groups
    groups.update(self._load_dj_groups())
    return groups
```

Add helper methods `_load_dj_aliases()` and `_load_dj_groups()` that instantiate a `DjCache` and call its `derive_artist_aliases()` / `derive_artist_groups()` methods.

**Step 5: Write analyzer tests**

Add tests that verify:
- File with `tracklists_artists = "Armin van Buuren|KI/KI"` gets `artist = "Armin van Buuren"` and `display_artist = "Armin van Buuren & KI/KI"`
- File with `tracklists_artists = "Dimitri Vegas & Like Mike"` gets `artist = "Dimitri Vegas & Like Mike"` and `display_artist = "Dimitri Vegas & Like Mike"`
- File without `tracklists_artists` falls back to filename/title parsing
- File with `tracklists_festival` still gets correct festival and edition
- Edition is empty for AMF, ASOT, WBH (the original bug)

**Step 6: Run all tests**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 7: Commit**

```
refactor(analyzer): use dedicated tags for all 1001TL metadata, remove title parser

The parse_1001tracklists_title function tried to re-decompose a flat
title string that the h1 parser already decomposed correctly. This caused
venue/conference/country data to leak into the edition field, producing
unwanted second lines on festival album posters.

All metadata now comes from dedicated tags:
- artist from CRATEDIGGER_1001TL_ARTISTS
- festival from CRATEDIGGER_1001TL_FESTIVAL
- stage from CRATEDIGGER_1001TL_STAGE
- venue from CRATEDIGGER_1001TL_VENUE
- date from CRATEDIGGER_1001TL_DATE
- edition from resolve_festival_with_edition() on festival tag
```

---

### Task 7: Fix config.json trailing comma

**Files:**
- Modify: `config.json:136`

**Step 1: Fix the trailing comma**

Change line 136 from `},` to `}` (remove trailing comma before closing brace).

**Step 2: Verify**

```python
python3 -c "import json; json.load(open('config.json')); print('OK')"
```

**Step 3: Run all tests**

Run: `pytest tests/ -x -q`
Expected: all pass

**Step 4: Commit**

```
fix(config): remove trailing comma that prevented config.json from loading
```

---

### Task 8: End-to-end verification against test data

**Files:**
- No code changes, verification only

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: all pass, no title parser tests remaining

**Step 2: Verify with real data**

Write a one-off script that loads the mediainfo_metadata.json and runs the analyzer for each file, checking that:
- ASOT: `edition` is empty, `festival` comes from filename (no FESTIVAL tag)
- AMF: `edition` is empty, `festival` is "AMF"
- WBH: `edition` is empty, `festival` comes from filename (no FESTIVAL tag)
- Tomorrowland Belgium: `edition` is "Belgium" (from `resolve_festival_with_edition("Tomorrowland Weekend 1")`)
- Armin & KI/KI: `artist` is "Armin van Buuren", `display_artist` is "Armin van Buuren & KI/KI"
- DVLM: `artist` is "Dimitri Vegas & Like Mike", `display_artist` is "Dimitri Vegas & Like Mike"

Note: ASOT and WBH will only get `CRATEDIGGER_1001TL_FESTIVAL` tags after re-running the chapters command with the promotion logic (Task 3). Until then, they rely on filename parsing for festival.

**Step 3: Create updated zip for Windows testing**

```bash
zip -r /home/martijn/_temp/cratedigger/CrateDigger.zip . -x '.git/*' '__pycache__/*' '*.pyc' '.claude/*' '.venv/*' '.worktrees/*' '*.egg-info/*'
```
