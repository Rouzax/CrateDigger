# Artist Groups & Double Extension Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add artist alias resolution and group detection so permanent acts stay intact and B2B sets file under the primary artist. Also fix the `.mkv.mkv` double extension bug in organize.

**Architecture:** Config-driven artist aliases + groups, resolved early in analyzer.py. `split_artists()` becomes groups-aware. `cli.py` stops double-appending file extensions.

**Tech Stack:** Python, dataclasses, regex, pytest

---

### Task 1: Fix double extension bug in cli.py

**Files:**
- Modify: `festival_organizer/cli.py:215,223`

`render_filename()` already returns the full filename with extension (e.g. `"2025 - EDC Las Vegas - AFROJACK.mkv"`). But `cli.py:215` and `cli.py:223` do `safe_filename(target_name) + mf.extension`, appending `.mkv` again.

**Step 1: Write the failing test**

Add to `tests/test_cli.py` (or `tests/test_templates.py` if no cli test file exists):

```python
def test_organize_target_no_double_extension():
    """render_filename() includes extension — cli should not append again."""
    from festival_organizer.templates import render_filename
    mf = MediaFile(
        source_path=Path("test.mkv"),
        artist="AFROJACK", festival="EDC Las Vegas", year="2025",
        extension=".mkv", content_type="festival_set",
    )
    name = render_filename(mf, CFG)
    assert name == "2025 - EDC Las Vegas - AFROJACK.mkv"
    assert not name.endswith(".mkv.mkv")
```

**Step 2: Fix cli.py**

Change lines 215 and 223 from:
```python
target = output / target_folder / (safe_filename(target_name) + mf.extension)
```
To:
```python
target = output / target_folder / target_name
```

`render_filename()` already calls `safe_filename()` internally and appends the extension.

**Step 3: Run tests**

Run: `python3 -m pytest tests/ -q`

**Step 4: Commit**

```
fix: remove double extension append in organize/scan commands
```

---

### Task 2: Add artist_aliases and artist_groups to config

**Files:**
- Modify: `festival_organizer/config.py` (DEFAULT_CONFIG + new properties/methods)
- Modify: `config.example.json`

**Step 1: Write failing tests**

Add to `tests/test_config.py`:

```python
def test_resolve_artist_alias():
    config = Config({"artist_aliases": {"DVLM": "Dimitri Vegas & Like Mike", "Area21": "Martin Garrix"}})
    assert config.resolve_artist("DVLM") == "Dimitri Vegas & Like Mike"
    assert config.resolve_artist("Area21") == "Martin Garrix"
    assert config.resolve_artist("Hardwell") == "Hardwell"  # passthrough


def test_resolve_artist_case_insensitive():
    config = Config({"artist_aliases": {"dvlm": "Dimitri Vegas & Like Mike"}})
    assert config.resolve_artist("DVLM") == "Dimitri Vegas & Like Mike"


def test_resolve_artist_b2b_not_in_groups():
    config = Config({"artist_groups": ["Dimitri Vegas & Like Mike"]})
    # B2B not in groups → return first artist
    assert config.resolve_artist("Armin van Buuren & KIKI") == "Armin van Buuren"


def test_resolve_artist_group_stays_intact():
    config = Config({"artist_groups": ["Dimitri Vegas & Like Mike"]})
    assert config.resolve_artist("Dimitri Vegas & Like Mike") == "Dimitri Vegas & Like Mike"


def test_resolve_artist_alias_then_group():
    config = Config({
        "artist_aliases": {"DVLM": "Dimitri Vegas & Like Mike"},
        "artist_groups": ["Dimitri Vegas & Like Mike"],
    })
    assert config.resolve_artist("DVLM") == "Dimitri Vegas & Like Mike"
```

**Step 2: Run tests — should fail**

**Step 3: Add to DEFAULT_CONFIG** (around line 130 in config.py):

```python
"artist_aliases": {},
"artist_groups": [],
```

**Step 4: Add properties and method to Config class:**

```python
@property
def artist_aliases(self) -> dict[str, str]:
    return self._data.get("artist_aliases", {})

@property
def artist_groups(self) -> set[str]:
    return {g.lower() for g in self._data.get("artist_groups", [])}

def resolve_artist(self, name: str) -> str:
    """Resolve artist alias, then for B2Bs not in groups return first artist."""
    # 1. Resolve alias (case-insensitive)
    if name in self.artist_aliases:
        name = self.artist_aliases[name]
    else:
        lower_map = {k.lower(): v for k, v in self.artist_aliases.items()}
        name = lower_map.get(name.lower(), name)

    # 2. If the full name is a known group, keep it
    if name.lower() in self.artist_groups:
        return name

    # 3. Split on separators, return first artist
    import re
    parts = re.split(r"\s+(?:&|B2B|b2b|vs\.?|x)\s+", name, flags=re.IGNORECASE)
    if len(parts) > 1:
        return parts[0].strip()

    return name
```

**Step 5: Update config.example.json** with example entries.

**Step 6: Run tests — should pass**

**Step 7: Commit**

```
feat: add artist_aliases and artist_groups config with resolve_artist()
```

---

### Task 3: Wire artist resolution into analyzer

**Files:**
- Modify: `festival_organizer/analyzer.py:96`

**Step 1: Write failing test**

Add to `tests/test_analyzer.py`:

```python
def test_analyzer_resolves_artist_b2b(tmp_path):
    """B2B artist names should resolve to primary artist."""
    # This test verifies the integration — config with no groups
    # should split "A & B" to "A"
    # (exact test depends on existing analyzer test patterns)
```

**Step 2: Add resolution after line 96**

After `artist = normalise_name(info.get("artist", ""))`, add:
```python
if artist:
    artist = config.resolve_artist(artist)
```

This follows the same pattern as `festival = config.resolve_festival_alias(festival)` on line 100.

**Step 3: Run tests**

**Step 4: Commit**

```
feat: resolve artist aliases and B2B names early in analyzer
```

---

### Task 4: Make split_artists() groups-aware

**Files:**
- Modify: `festival_organizer/fanart.py:285-298`
- Modify: `festival_organizer/operations.py` (callers of split_artists)

**Step 1: Write failing test**

Add to `tests/test_fanart.py`:

```python
def test_split_artists_respects_groups():
    groups = {"dimitri vegas & like mike"}
    result = split_artists("Dimitri Vegas & Like Mike", groups=groups)
    assert result == ["Dimitri Vegas & Like Mike"]


def test_split_artists_splits_non_groups():
    groups = {"dimitri vegas & like mike"}
    result = split_artists("Armin van Buuren & KIKI", groups=groups)
    assert result == ["Armin van Buuren", "KIKI"]
```

**Step 2: Update split_artists signature**

```python
def split_artists(name: str, groups: set[str] | None = None) -> list[str]:
    # If the full name is a known group, don't split
    if groups and name.lower() in groups:
        return [name]
    # ... rest unchanged
```

**Step 3: Update callers in operations.py**

`FanartOperation.execute()` — pass `self.config.artist_groups` to `split_artists()`.

**Step 4: Run tests**

**Step 5: Commit**

```
feat: split_artists() respects artist_groups config
```

---

### Task 5: Add default artist groups to config

**Files:**
- Modify: `festival_organizer/config.py` (DEFAULT_CONFIG)

Add well-known permanent acts to the default groups list:

```python
"artist_groups": [
    "Above & Beyond",
    "Axwell & Ingrosso",
    "Dimitri Vegas & Like Mike",
    "Galantis",
    "Sunnery James & Ryan Marciano",
    "Swedish House Mafia",
    "Vini Vici",
],
```

**Step 1: Add to DEFAULT_CONFIG**

**Step 2: Run full test suite**

**Step 3: Commit**

```
feat: add default artist_groups for known permanent acts
```

---

## Verification

1. `python3 -m pytest tests/ -q` — all tests pass
2. Manual: organize a folder with "Armin van Buuren & KIKI" → file goes to "Armin van Buuren/" folder, no `.mkv.mkv`
3. Manual: organize a folder with "Dimitri Vegas & Like Mike" → file stays in "Dimitri Vegas & Like Mike/" folder
4. Manual: fanart lookup for "Dimitri Vegas & Like Mike" → single lookup, not split
5. Manual: fanart lookup for "Armin van Buuren & KIKI" → looks up "Armin van Buuren" only

## Critical files

| File | Change |
|------|--------|
| `festival_organizer/cli.py` | Remove double extension append |
| `festival_organizer/config.py` | Add artist_aliases, artist_groups, resolve_artist() |
| `festival_organizer/analyzer.py` | Wire resolve_artist() after normalise_name() |
| `festival_organizer/fanart.py` | Groups-aware split_artists() |
| `festival_organizer/operations.py` | Pass groups to split_artists() |
| `config.example.json` | Add example config |
