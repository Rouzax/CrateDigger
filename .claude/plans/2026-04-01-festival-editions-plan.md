# Festival Editions Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename the "location" concept to "edition" across the entire codebase, fix edition-based resolution so "Tomorrowland Winter" resolves correctly, and clean up alias duplication.

**Architecture:** Config layer changes drive everything. The `known_locations` config key becomes `editions`, the `location_in_name` flag is removed, `resolve_festival_with_edition()` adds decomposition-based resolution, and `MediaFile.location` becomes `MediaFile.edition`. Downstream consumers get mechanical renames.

**Tech Stack:** Python 3.12, pytest, dataclasses

---

### Task 1: Update festivals.example.json

**Files:**
- Modify: `festivals.example.json`

**Step 1: Update the config section**

Replace the config section with editions key, remove `location_in_name` flags:

```json
"config": {
    "Tomorrowland": {
        "editions": ["Belgium", "Brasil", "Winter"]
    },
    "Dreamstate": {
        "editions": ["SoCal", "Europe", "Australia", "Mexico"]
    },
    "EDC": {
        "editions": ["Las Vegas", "Mexico", "Orlando", "Thailand"]
    },
    "We Belong Here": {
        "editions": ["Miami", "Tulum"]
    },
    "Ultra Music Festival": {
        "editions": ["Miami", "Europe", "Japan", "Korea", "Singapore", "South Africa", "Australia"]
    }
}
```

**Step 2: Clean up aliases**

Remove edition combos from aliases. Keep only abbreviations and genuinely alternate names:

```json
"aliases": {
    "ADE": ["Amsterdam Dance Event"],
    "AMF": ["Amsterdam Music Festival"],
    "ASOT": ["A State Of Trance"],
    "Awakenings": [],
    "Balaton Sound": [],
    "Coachella": [],
    "Creamfields": [],
    "Dance Valley": [],
    "Decibel Outdoor": [],
    "Defqon.1": [],
    "Dreamstate": [],
    "EDC": ["Electric Daisy Carnival"],
    "Electric Zoo": ["EZoo"],
    "Exit Festival": ["EXIT"],
    "Glastonbury": [],
    "Lollapalooza": [],
    "Mysteryland": [],
    "Nature One": [],
    "Parookaville": [],
    "Red Rocks": ["Red Rocks Amphitheatre"],
    "Sensation": [],
    "Sziget": [],
    "Tomorrowland": ["Tomorrowland Weekend 1", "Tomorrowland Weekend 2", "TML"],
    "Ultra Music Festival": ["Ultra", "UMF"],
    "Untold": [],
    "We Belong Here": [],
    "World Club Dome": []
}
```

**Step 3: Commit**

```bash
git add festivals.example.json
git commit -m "refactor: rename known_locations to editions in festival config"
```

---

### Task 2: Core config methods (TDD)

**Files:**
- Modify: `festival_organizer/config.py:206-229,284-287,349-360`
- Test: `tests/test_config.py`

**Step 1: Write failing tests for new edition resolution**

Add to `tests/test_config.py`. These tests target the new behavior: edition decomposition without aliases.

```python
def test_resolve_festival_with_edition():
    cfg = Config(TEST_CONFIG)
    # Edition decomposition (no alias needed)
    assert cfg.resolve_festival_with_edition("Tomorrowland Winter") == ("Tomorrowland", "Winter")
    assert cfg.resolve_festival_with_edition("Tomorrowland Belgium") == ("Tomorrowland", "Belgium")
    assert cfg.resolve_festival_with_edition("EDC Las Vegas") == ("EDC", "Las Vegas")
    assert cfg.resolve_festival_with_edition("Dreamstate SoCal") == ("Dreamstate", "SoCal")
    assert cfg.resolve_festival_with_edition("Dreamstate Europe") == ("Dreamstate", "Europe")
    # Alias prefix + edition (Ultra is alias for Ultra Music Festival)
    assert cfg.resolve_festival_with_edition("Ultra Europe") == ("Ultra Music Festival", "Europe")
    assert cfg.resolve_festival_with_edition("Ultra Music Festival Miami") == ("Ultra Music Festival", "Miami")
    # Pure alias (no edition)
    assert cfg.resolve_festival_with_edition("TML") == ("Tomorrowland", "")
    assert cfg.resolve_festival_with_edition("AMF") == ("AMF", "")
    # Alias that collapses weekends (no edition extracted)
    assert cfg.resolve_festival_with_edition("Tomorrowland Weekend 1") == ("Tomorrowland", "")
    # Genuine alternate name (not an edition)
    assert cfg.resolve_festival_with_edition("Red Rocks Amphitheatre") == ("Red Rocks", "")
    # Unknown festival
    assert cfg.resolve_festival_with_edition("Unknown Fest") == ("Unknown Fest", "")


def test_resolve_festival_with_edition_case_insensitive():
    cfg = Config(TEST_CONFIG)
    assert cfg.resolve_festival_with_edition("tomorrowland winter") == ("Tomorrowland", "Winter")
    assert cfg.resolve_festival_with_edition("EDC LAS VEGAS") == ("EDC", "Las Vegas")


def test_known_festivals_includes_edition_combos():
    cfg = Config(TEST_CONFIG)
    known = cfg.known_festivals
    # Canonical names
    assert "Tomorrowland" in known
    assert "EDC" in known
    # Edition combos (generated dynamically)
    assert "Tomorrowland Winter" in known
    assert "Tomorrowland Belgium" in known
    assert "EDC Las Vegas" in known
    # Aliases
    assert "TML" in known
    assert "Ultra" in known


def test_get_festival_display_with_editions():
    cfg = Config(TEST_CONFIG)
    assert cfg.get_festival_display("Tomorrowland", "Belgium") == "Tomorrowland Belgium"
    assert cfg.get_festival_display("Tomorrowland", "Winter") == "Tomorrowland Winter"
    assert cfg.get_festival_display("Tomorrowland", "") == "Tomorrowland"
    # AMF has no editions configured
    assert cfg.get_festival_display("AMF", "Netherlands") == "AMF"
    # Unknown edition rejected
    assert cfg.get_festival_display("Dreamstate", "United States") == "Dreamstate"
    assert cfg.get_festival_display("Dreamstate", "SoCal") == "Dreamstate SoCal"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py::test_resolve_festival_with_edition tests/test_config.py::test_resolve_festival_with_edition_case_insensitive tests/test_config.py::test_known_festivals_includes_edition_combos tests/test_config.py::test_get_festival_display_with_editions -v`
Expected: FAIL (methods don't exist yet)

**Step 3: Implement config changes**

In `festival_organizer/config.py`:

Replace `all_known_locations` property (lines 206-213) with:

```python
@property
def all_known_editions(self) -> set[str]:
    """Collect all editions from every festival config entry."""
    editions = set()
    for fc in self.festival_config.values():
        for ed in fc.get("editions", []):
            editions.add(ed)
    return editions
```

Replace `resolve_festival_with_location` method (lines 215-229) with:

```python
def resolve_festival_with_edition(self, name: str) -> tuple[str, str]:
    """Resolve alias and extract edition from the name if applicable.

    Returns (canonical_festival, edition).
    "Dreamstate SoCal" -> ("Dreamstate", "SoCal")
    "Tomorrowland Winter" -> ("Tomorrowland", "Winter")
    "TML" -> ("Tomorrowland", "")
    """
    canonical = self.resolve_festival_alias(name)

    # Alias resolved to something different: check for edition suffix
    if canonical != name:
        fc = self.festival_config.get(canonical, {})
        suffix = name[len(canonical):].strip() if name.lower().startswith(canonical.lower()) else ""
        for ed in fc.get("editions", []):
            if ed.lower() == suffix.lower():
                return canonical, ed
        return canonical, ""

    # No alias match. Try canonical + edition decomposition.
    for fest_name, fc in self.festival_config.items():
        for ed in fc.get("editions", []):
            if f"{fest_name} {ed}".lower() == name.lower():
                return fest_name, ed

    # Try alias prefixes (handles "Ultra Europe" -> alias "Ultra" + edition "Europe")
    for alias, canon in self.festival_aliases.items():
        fc = self.festival_config.get(canon, {})
        for ed in fc.get("editions", []):
            if f"{alias} {ed}".lower() == name.lower():
                return canon, ed

    return name, ""
```

Replace `known_festivals` property (lines 284-287) with:

```python
@property
def known_festivals(self) -> set[str]:
    """All festival names the system can recognize."""
    names = set(self.festival_aliases.keys())
    names.update(self.festival_aliases.values())
    for fest_name, fc in self.festival_config.items():
        for ed in fc.get("editions", []):
            names.add(f"{fest_name} {ed}")
    return names
```

Replace `get_festival_display` method (lines 349-360) with:

```python
def get_festival_display(self, canonical_festival: str, edition: str) -> str:
    """Get display name for a festival, optionally including edition."""
    fc = self.festival_config.get(canonical_festival, {})
    editions = fc.get("editions", [])
    if editions and edition:
        for ed in editions:
            if ed.lower() == edition.lower():
                return f"{canonical_festival} {ed}"
    return canonical_festival
```

**Step 4: Run new tests to verify they pass**

Run: `python -m pytest tests/test_config.py::test_resolve_festival_with_edition tests/test_config.py::test_resolve_festival_with_edition_case_insensitive tests/test_config.py::test_known_festivals_includes_edition_combos tests/test_config.py::test_get_festival_display_with_editions -v`
Expected: PASS

**Step 5: Update existing config tests**

In `tests/test_config.py`:

Replace `test_config_festival_aliases` (line 19-24):

```python
def test_config_festival_aliases():
    cfg = Config(TEST_CONFIG)
    assert cfg.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    assert cfg.resolve_festival_alias("amf") == "AMF"
    # "EDC Las Vegas" is no longer an alias; resolved via edition decomposition
    assert cfg.resolve_festival_alias("EDC Las Vegas") == "EDC Las Vegas"
    assert cfg.resolve_festival_alias("Unknown Thing") == "Unknown Thing"
```

Replace `test_config_festival_location` (line 27-33):

```python
def test_config_festival_edition():
    cfg = Config(TEST_CONFIG)
    # Tomorrowland has editions configured
    assert cfg.get_festival_display("Tomorrowland", "Belgium") == "Tomorrowland Belgium"
    assert cfg.get_festival_display("Tomorrowland", "") == "Tomorrowland"
    # AMF has no editions
    assert cfg.get_festival_display("AMF", "Netherlands") == "AMF"
```

Replace `test_get_festival_display_rejects_unknown_location` (line 36-41):

```python
def test_get_festival_display_rejects_unknown_edition():
    cfg = Config(TEST_CONFIG)
    # Dreamstate has editions: [SoCal, Europe, Australia, Mexico]
    # "United States" is not in that list, should be omitted
    assert cfg.get_festival_display("Dreamstate", "United States") == "Dreamstate"
    assert cfg.get_festival_display("Dreamstate", "SoCal") == "Dreamstate SoCal"
```

Remove `test_resolve_festival_with_location` (line 44-54) entirely. Its coverage is replaced by the new `test_resolve_festival_with_edition`.

**Step 6: Run all config tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add festival_organizer/config.py tests/test_config.py
git commit -m "refactor: replace location with edition in config resolution"
```

---

### Task 3: Data model rename

**Files:**
- Modify: `festival_organizer/models.py:21`

**Step 1: Rename field**

In `festival_organizer/models.py`, change line 21:

```python
    edition: str = ""
```

(was `location: str = ""`)

**Step 2: Commit**

```bash
git add festival_organizer/models.py
git commit -m "refactor: rename MediaFile.location to MediaFile.edition"
```

Note: this will temporarily break many files. The next tasks fix each consumer.

---

### Task 4: Analyzer rename

**Files:**
- Modify: `festival_organizer/analyzer.py:54,89,106-111,162`

**Step 1: Apply renames**

Line 54: `"location": "",` -> `"edition": "",`

Line 89: `for key in ["artist", "festival", "date", "year", "stage", "location"]:` -> `for key in ["artist", "festival", "date", "year", "stage", "edition"]:`

Lines 106-111:
```python
    if meta.get("tracklists_festival"):
        fest, ed = config.resolve_festival_with_edition(
            meta["tracklists_festival"]
        )
        info["festival"] = fest
        if ed:
            info["edition"] = ed
```

Line 162: `location=info.get("location", ""),` -> `edition=info.get("edition", ""),`

**Step 2: Commit**

```bash
git add festival_organizer/analyzer.py
git commit -m "refactor: rename location to edition in analyzer"
```

---

### Task 5: Parsers rename

**Files:**
- Modify: `festival_organizer/parsers.py`
- Test: `tests/test_parsers.py`

**Step 1: Rename all location references in parsers.py**

Line 35 docstring: `"Returns dict with keys: artist, festival, stage, edition, date, year."`

Line 70: `fest, alias_ed = config.resolve_festival_with_edition(seg.strip())`
Line 73: `result["edition"] = alias_ed`

Line 84: `known_eds = config.all_known_editions`
Line 87: `for ed in known_eds:` (was `for loc in known_locs:`)
Line 88: `if ed.lower() in seg.lower():` (was `if loc.lower() in seg.lower():`)

Lines 98, 109, 111, 117, 119: all `result.setdefault("location", ...)` -> `result.setdefault("edition", ...)`

Line 121 comment: `"# No known festival; first segment is venue/festival, rest is edition"`
Line 123: `result["edition"] = ", ".join(segments[1:])`

Lines 172, 176, 178 comments: update "location" -> "edition"

Line 179: `for ed in config.all_known_editions:`
Line 180: `if ed.lower() == part2.lower():`
Line 181: `result["edition"] = part2`

Line 297 comment: `"# Known edition"`
Line 298: `for ed in config.all_known_editions:`
Line 299: `if ed.lower() in part.lower():`
Line 300: `result.setdefault("edition", ed)`

**Step 2: Update parser tests**

In `tests/test_parsers.py`:

Line 28: `assert "Johan Cruijff ArenA" in result.get("edition", "")`
Line 38: `assert result["edition"] == "Belgium"`
Line 82: `assert result["edition"] == "SoCal"`

Rename function (line 74): `def test_1001tl_dreamstate_socal_edition():`
Update docstring (line 75): `"""Edition should come from festival alias, not country."""`

Rename function (line 88): `def test_1001tl_edc_las_vegas_edition():`
Update docstring (line 89): `"""EDC Las Vegas should extract Las Vegas as edition."""`
Line 96: `assert result["edition"] == "Las Vegas"`

Rename function (line 177): `def test_parent_dirs_tomorrowland_edition():`
Line 184: `assert result.get("edition") == "Belgium"`

**Step 3: Run parser tests**

Run: `python -m pytest tests/test_parsers.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add festival_organizer/parsers.py tests/test_parsers.py
git commit -m "refactor: rename location to edition in parsers"
```

---

### Task 6: Templates rename

**Files:**
- Modify: `festival_organizer/templates.py:65,68,80`
- Test: `tests/test_templates.py`

**Step 1: Apply renames in templates.py**

Line 65 comment: `"# Resolve festival display name (with edition if configured)"`
Line 68: `festival = config.get_festival_display(festival, media_file.edition)`
Line 80: `"edition": safe_filename(media_file.edition),`

**Step 2: Update template tests**

In `tests/test_templates.py`:

Line 52: `edition="Belgium",` (was `location="Belgium",`)
Line 56 comment: `"# Tomorrowland has editions, so becomes \"Tomorrowland Belgium\""`
Line 88 function name: `def test_render_folder_with_edition_in_festival_name():`
Line 94: `edition="Brasil",` (was `location="Brasil",`)
Line 142: `edition="Belgium",` (was `location="Belgium",`)

**Step 3: Run template tests**

Run: `python -m pytest tests/test_templates.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add festival_organizer/templates.py tests/test_templates.py
git commit -m "refactor: rename location to edition in templates"
```

---

### Task 7: NFO rename

**Files:**
- Modify: `festival_organizer/nfo.py:47-48,79-80,90-91`
- Test: `tests/test_nfo.py`

**Step 1: Apply renames in nfo.py**

Lines 47-48:
```python
    if mf.edition:
        festival_display = config.get_festival_display(mf.festival, mf.edition)
```

Lines 79-80:
```python
    if mf.edition:
        _add(root, "tag", mf.edition)
```

Lines 90-91:
```python
    if mf.edition:
        plot_parts.append(f"Edition: {mf.edition}")
```

**Step 2: Update NFO tests**

In `tests/test_nfo.py`:

Line 57 docstring: `"""tag elements for content type, festival, edition."""`
Line 59: `edition="Belgium",` (was `location="Belgium",`)
Line 97: `edition="Belgium",` (was `location="Belgium",`)

**Step 3: Run NFO tests**

Run: `python -m pytest tests/test_nfo.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add festival_organizer/nfo.py tests/test_nfo.py
git commit -m "refactor: rename location to edition in NFO generation"
```

---

### Task 8: Operations rename

**Files:**
- Modify: `festival_organizer/operations.py:192-194,478-480,531`

**Step 1: Apply renames**

Lines 191-195:
```python
            festival_display = mf.festival
            if mf.edition:
                festival_display = self.config.get_festival_display(
                    mf.festival, mf.edition
                )
```

Lines 477-481:
```python
            festival_display = mf.festival
            if mf.edition:
                festival_display = self.config.get_festival_display(
                    mf.festival, mf.edition
                )
```

Line 531: `detail=mf.stage or mf.edition or "",`

**Step 2: Commit**

```bash
git add festival_organizer/operations.py
git commit -m "refactor: rename location to edition in operations"
```

---

### Task 9: Logging rename

**Files:**
- Modify: `festival_organizer/logging_util.py:25,53`

**Step 1: Apply renames**

Line 25: `"stage", "edition", "content_type", "file_type",` (was `"stage", "location", ...`)
Line 53: `"edition": mf.edition,` (was `"location": mf.location,`)

**Step 2: Commit**

```bash
git add festival_organizer/logging_util.py
git commit -m "refactor: rename location to edition in logging"
```

---

### Task 10: Remaining test files

**Files:**
- Modify: `tests/test_planner.py:57`
- Modify: `tests/test_integration.py:73`

**Step 1: Update test_planner.py**

Line 57: `edition="Belgium",` (was `location="Belgium",`)

**Step 2: Update test_integration.py**

Line 73: `assert mf.edition == "Belgium"` (was `assert mf.location == "Belgium"`)

**Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_planner.py tests/test_integration.py
git commit -m "refactor: rename location to edition in remaining tests"
```

---

### Task 11: Final verification

**Step 1: Run full test suite one more time**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

**Step 2: Grep for any remaining "location" references that should have been renamed**

Run: `grep -rn "known_locations\|location_in_name\|all_known_locations\|resolve_festival_with_location\|mf\.location\|media_file\.location\|\"location\"" festival_organizer/ tests/ --include="*.py" | grep -v "\.pyc"`

Expected: No matches in production code. The only remaining "location" references should be in comments or unrelated contexts (e.g., file system locations, not the edition concept).

**Step 3: Verify key resolution cases in REPL**

Run:
```bash
python -c "
from tests.conftest import TEST_CONFIG
from festival_organizer.config import Config
cfg = Config(TEST_CONFIG)
cases = [
    ('Tomorrowland Winter', ('Tomorrowland', 'Winter')),
    ('Tomorrowland Belgium', ('Tomorrowland', 'Belgium')),
    ('EDC Las Vegas', ('EDC', 'Las Vegas')),
    ('Ultra Europe', ('Ultra Music Festival', 'Europe')),
    ('TML', ('Tomorrowland', '')),
    ('Tomorrowland Weekend 1', ('Tomorrowland', '')),
    ('AMF', ('AMF', '')),
    ('Red Rocks Amphitheatre', ('Red Rocks', '')),
    ('Unknown Fest', ('Unknown Fest', '')),
]
for input_name, expected in cases:
    result = cfg.resolve_festival_with_edition(input_name)
    status = 'OK' if result == expected else 'FAIL'
    print(f'{status}: {input_name!r} -> {result} (expected {expected})')
"
```
Expected: All OK
