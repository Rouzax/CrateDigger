# Grouped Config Format for Artists & Festivals

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor `artists.json` and `festivals.json` from flat `alias→canonical` maps to grouped `canonical→[aliases]` format, and populate both with comprehensive EDM scene knowledge.

**Architecture:** Change the JSON file format to `{"Canonical Name": ["alias1", "alias2"]}`. At load time, invert into the existing flat lookup map so `resolve_festival_alias()` and `resolve_artist()` don't change. Backwards compat: if the old flat format is detected in `self._data`, convert it on the fly.

**Tech Stack:** Python, JSON, pytest

---

### Task 1: Change `_FESTIVAL_DEFAULTS` to grouped format and add inverter

**Files:**
- Modify: `festival_organizer/config.py:23-58` (_FESTIVAL_DEFAULTS)
- Modify: `festival_organizer/config.py:197-201` (festival_aliases property)
- Test: `tests/test_config.py`

**Step 1: Write failing test**

Add to `tests/test_config.py`:

```python
def test_festival_aliases_grouped_format():
    """Grouped format: canonical -> [aliases] gets inverted to alias -> canonical."""
    config = Config({
        "festival_aliases": {
            "Tomorrowland": ["TML", "Tomorrowland Weekend 1", "Tomorrowland Weekend 2"],
            "AMF": ["Amsterdam Music Festival"],
        }
    })
    assert config.resolve_festival_alias("TML") == "Tomorrowland"
    assert config.resolve_festival_alias("Tomorrowland Weekend 1") == "Tomorrowland"
    assert config.resolve_festival_alias("Amsterdam Music Festival") == "AMF"
    # Canonical names resolve to themselves
    assert config.resolve_festival_alias("Tomorrowland") == "Tomorrowland"
    assert config.resolve_festival_alias("AMF") == "AMF"
```

**Step 2: Run test — should fail**

Run: `python3 -m pytest tests/test_config.py::test_festival_aliases_grouped_format -v`

**Step 3: Add `_invert_alias_map()` helper and update config**

Add module-level helper to `config.py`:

```python
def _invert_alias_map(grouped: dict) -> dict[str, str]:
    """Convert {canonical: [aliases]} to {alias: canonical} flat map.

    Also maps each canonical name to itself.
    Detects old flat format (values are strings not lists) and passes through.
    """
    flat = {}
    for key, value in grouped.items():
        if isinstance(value, list):
            # New grouped format
            flat[key] = key  # canonical maps to itself
            for alias in value:
                flat[alias] = key
        else:
            # Old flat format: {alias: canonical}
            flat[key] = value
    return flat
```

Change `_FESTIVAL_DEFAULTS` to grouped format:

```python
_FESTIVAL_DEFAULTS = {
    "aliases": {
        "AMF": ["Amsterdam Music Festival"],
        "EDC Las Vegas": ["EDC", "Electric Daisy Carnival"],
        "Ultra Music Festival": ["Ultra", "Ultra Music Festival Miami", "UMF"],
        "Tomorrowland": ["Tomorrowland Weekend 1", "Tomorrowland Weekend 2", "TML"],
        "Mysteryland": [],
        "Glastonbury": [],
        "Red Rocks": ["Red Rocks Amphitheatre"],
        "Dreamstate": ["Dreamstate SoCal"],
        "We Belong Here": ["We Belong Here Miami"],
        "Defqon.1": [],
        "Creamfields": [],
        "Lollapalooza": [],
        "Untold": [],
        "Sensation": [],
        "Parookaville": [],
        "Awakenings": [],
        "Dance Valley": [],
        "Burning Man": [],
        "Coachella": [],
        "Electric Zoo": ["EZoo"],
        "Sonar": [],
        "ADE": ["Amsterdam Dance Event"],
        "ASOT": ["A State Of Trance"],
        "Nature One": [],
        "Decibel Outdoor": [],
        "Airbeat One": [],
        "World Club Dome": [],
        "Sunrise Festival": [],
        "Exit Festival": ["EXIT"],
        "Balaton Sound": [],
        "Sziget": [],
        "Medusa Festival": [],
    },
    "config": {
        "Tomorrowland": {
            "location_in_name": True,
            "known_locations": ["Belgium", "Brasil", "Brazil"],
        },
        "EDC Las Vegas": {
            "location_in_name": True,
            "known_locations": ["Las Vegas", "Mexico", "Orlando", "Thailand"],
        },
    },
}
```

Update `festival_aliases` property to use `_invert_alias_map()`:

```python
@property
def festival_aliases(self) -> dict[str, str]:
    defaults = _invert_alias_map(
        self._load_external_config("festivals.json", _FESTIVAL_DEFAULTS).get("aliases", {})
    )
    if "festival_aliases" in self._data:
        return {**defaults, **_invert_alias_map(self._data["festival_aliases"])}
    return defaults
```

**Step 4: Run all tests**

Run: `python3 -m pytest tests/ -q`

**Step 5: Commit**

```
refactor: festival aliases use grouped canonical->[aliases] format
```

---

### Task 2: Change `_ARTIST_DEFAULTS` to grouped format

**Files:**
- Modify: `festival_organizer/config.py:11-21` (_ARTIST_DEFAULTS)
- Modify: `festival_organizer/config.py:271-275` (artist_aliases property)
- Test: `tests/test_config.py`

**Step 1: Write failing test**

```python
def test_artist_aliases_grouped_format():
    """Grouped format: canonical -> [aliases] gets inverted."""
    config = Config({
        "artist_aliases": {
            "Martin Garrix": ["Area21", "YTRAM", "GRX"],
        }
    })
    assert config.resolve_artist("Area21") == "Martin Garrix"
    assert config.resolve_artist("YTRAM") == "Martin Garrix"
    assert config.resolve_artist("Martin Garrix") == "Martin Garrix"
```

**Step 2: Run test — should fail**

**Step 3: Update `_ARTIST_DEFAULTS` and property**

```python
_ARTIST_DEFAULTS = {
    "aliases": {
        "Martin Garrix": ["Area21", "YTRAM", "GRX"],
        "Tiësto": ["Tiesto", "VER:WEST", "VERWEST"],
        "David Guetta": ["Jack Back"],
        "Armin van Buuren": ["Gaia", "Rising Star"],
        "Nicky Romero": ["Monocule"],
        "Oliver Heldens": ["HI-LO"],
        "Afrojack": ["NLW"],
        "Hardwell": ["Revealed"],
        "Steve Aoki": [],
        "Marshmello": [],
        "Skrillex": [],
        "Deadmau5": ["deadmau5", "BSOD", "Testpilot"],
    },
    "groups": [
        "Above & Beyond",
        "Axwell & Ingrosso",
        "Dimitri Vegas & Like Mike",
        "Sunnery James & Ryan Marciano",
        "Swedish House Mafia",
        "Vini Vici",
        "Blasterjaxx",
        "Showtek",
        "W&W",
        "Sick Individuals",
        "Breathe Carolina",
        "Loud Luxury",
        "Galantis",
        "NERVO",
        "Cosmic Gate",
        "Aly & Fila",
        "Myon & Shane 54",
        "Gabriel & Dresden",
        "Chocolate Puma",
        "Da Tweekaz",
        "Sub Zero Project",
    ],
}
```

Update `artist_aliases` property:

```python
@property
def artist_aliases(self) -> dict[str, str]:
    defaults = _invert_alias_map(
        self._load_external_config("artists.json", _ARTIST_DEFAULTS).get("aliases", {})
    )
    if "artist_aliases" in self._data:
        return {**defaults, **_invert_alias_map(self._data["artist_aliases"])}
    return defaults
```

**Step 4: Run all tests**

Run: `python3 -m pytest tests/ -q`

**Step 5: Commit**

```
refactor: artist aliases use grouped canonical->[aliases] format
```

---

### Task 3: Update existing tests for new format

**Files:**
- Modify: `tests/test_config.py`

Some existing tests pass old-style flat dicts (`{"DVLM": "Dimitri Vegas & Like Mike"}`). The `_invert_alias_map()` detects the old format (string values vs list values) and passes through. Verify all existing tests still pass, fix any that don't.

**Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -q`

If any tests fail due to the format change, update them to use the new grouped format.

**Step 2: Commit if changes needed**

```
test: update config tests for grouped alias format
```

---

### Task 4: Update example JSON files

**Files:**
- Modify: `festivals.example.json`
- Modify: `artists.example.json`

**Step 1: Rewrite `festivals.example.json`**

```json
{
    "_comment": "Festival configuration. Place as festivals.json next to config.json or in ~/.cratedigger/",
    "aliases": {
        "AMF": ["Amsterdam Music Festival"],
        "EDC Las Vegas": ["EDC", "Electric Daisy Carnival"],
        "Ultra Music Festival": ["Ultra", "Ultra Music Festival Miami", "UMF"],
        "Tomorrowland": ["Tomorrowland Weekend 1", "Tomorrowland Weekend 2", "TML"],
        "Mysteryland": [],
        "Glastonbury": [],
        "Red Rocks": ["Red Rocks Amphitheatre"],
        "Dreamstate": ["Dreamstate SoCal"],
        "We Belong Here": ["We Belong Here Miami"],
        "Defqon.1": [],
        "Creamfields": [],
        "Lollapalooza": [],
        "Untold": [],
        "ADE": ["Amsterdam Dance Event"],
        "ASOT": ["A State Of Trance"],
        "Electric Zoo": ["EZoo"],
        "Sensation": [],
        "Parookaville": [],
        "Awakenings": []
    },
    "config": {
        "Tomorrowland": {
            "location_in_name": true,
            "known_locations": ["Belgium", "Brasil", "Brazil"]
        },
        "EDC Las Vegas": {
            "location_in_name": true,
            "known_locations": ["Las Vegas", "Mexico", "Orlando", "Thailand"]
        }
    }
}
```

**Step 2: Rewrite `artists.example.json`**

```json
{
    "_comment": "Artist configuration. Place as artists.json next to config.json or in ~/.cratedigger/",
    "aliases": {
        "Martin Garrix": ["Area21", "YTRAM", "GRX"],
        "Tiësto": ["Tiesto", "VER:WEST", "VERWEST"],
        "David Guetta": ["Jack Back"],
        "Armin van Buuren": ["Gaia", "Rising Star"],
        "Nicky Romero": ["Monocule"],
        "Oliver Heldens": ["HI-LO"],
        "Afrojack": ["NLW"],
        "Deadmau5": ["deadmau5", "BSOD", "Testpilot"]
    },
    "groups": [
        "Above & Beyond",
        "Axwell & Ingrosso",
        "Dimitri Vegas & Like Mike",
        "Sunnery James & Ryan Marciano",
        "Swedish House Mafia",
        "Vini Vici",
        "W&W",
        "Showtek",
        "NERVO",
        "Cosmic Gate",
        "Aly & Fila",
        "Galantis",
        "Da Tweekaz",
        "Sub Zero Project"
    ]
}
```

**Step 3: Run full test suite**

**Step 4: Commit**

```
docs: update example JSON files with grouped alias format and expanded entries
```

---

## Verification

1. `python3 -m pytest tests/ -q` — all tests pass
2. `resolve_festival_alias("Tomorrowland Weekend 1")` → `"Tomorrowland"`
3. `resolve_festival_alias("TML")` → `"Tomorrowland"`
4. `resolve_artist("Area21")` → `"Martin Garrix"`
5. `resolve_artist("DVLM")` → `"Dimitri Vegas & Like Mike"` (old format in self._data still works)
6. `known_festivals` includes all canonical names

## Critical files

| File | Change |
|------|--------|
| `festival_organizer/config.py` | Add `_invert_alias_map()`, update defaults to grouped format, update properties |
| `tests/test_config.py` | Add grouped format tests, update existing if needed |
| `festivals.example.json` | Rewrite in grouped format with expanded entries |
| `artists.example.json` | Rewrite in grouped format with expanded entries |
