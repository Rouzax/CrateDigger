# Festival Editions Refactor: Design

## Problem

Festival folder names like "Tomorrowland Belgium", "Tomorrowland Winter", "EDC Las Vegas" combine a canonical festival name with a suffix. The current config has three problems:

1. **Redundant data**: edition combos like "Dreamstate SoCal", "EDC Las Vegas" are duplicated in both the aliases list AND constructible from `config[canonical].known_locations`. Adding a new edition requires updating two places.
2. **Broken resolution**: "Tomorrowland Winter" does not resolve because it is not in aliases, and `resolve_festival_with_location()` has a `canonical != name` guard that blocks extraction when alias resolution returns the input unchanged.
3. **Semantic mismatch**: `known_locations` includes non-geographic values like "Winter". The field `MediaFile.location` stores edition values, not locations.

## Solution

Rename the concept from "location" to "edition" everywhere: config keys, methods, data model field. Remove the `location_in_name` flag (implied by non-empty editions list). Clean up alias duplication. Add edition-based decomposition to the resolution logic.

## Config File Changes (festivals.example.json)

### Aliases

Remove all `canonical + edition` entries. Keep only abbreviations and genuinely alternate names.

```
Before: "Tomorrowland": ["Tomorrowland Weekend 1", "Tomorrowland Weekend 2", "TML"]
After:  "Tomorrowland": ["Tomorrowland Weekend 1", "Tomorrowland Weekend 2", "TML"]

Before: "EDC": ["EDC Las Vegas", "Electric Daisy Carnival"]
After:  "EDC": ["Electric Daisy Carnival"]

Before: "Dreamstate": ["Dreamstate SoCal", "Dreamstate Europe", "Dreamstate Australia"]
After:  "Dreamstate": []

Before: "Ultra Music Festival": ["Ultra", "Ultra Music Festival Miami", "UMF", "Ultra Europe", ...]
After:  "Ultra Music Festival": ["Ultra", "UMF"]

Before: "We Belong Here": ["We Belong Here Miami", "We Belong Here Tulum"]
After:  "We Belong Here": []
```

Keep as-is: `"Red Rocks": ["Red Rocks Amphitheatre"]` (genuine alternate name, not edition).

### Config section

```
Before:
"Tomorrowland": { "location_in_name": true, "known_locations": ["Belgium", "Brasil", "Brazil"] }

After:
"Tomorrowland": { "editions": ["Belgium", "Brasil", "Winter"] }
```

Same pattern for EDC, Dreamstate, Ultra Music Festival, We Belong Here. Drop "Brazil" duplicate (keep "Brasil"). Remove `location_in_name` flag everywhere.

## Resolution Logic (config.py)

`resolve_festival_with_edition()` replaces `resolve_festival_with_location()`. Four-step resolution:

1. **Alias lookup**: try `resolve_festival_alias(name)`. If it resolves to a different canonical, check if any edition appears as a suffix in the original name. Return `(canonical, edition)` or `(canonical, "")`.
2. **Canonical + edition decomposition**: for each festival with editions, check if `name` matches `canonical + " " + edition` (case-insensitive exact match). Handles "Tomorrowland Winter", "EDC Las Vegas".
3. **Alias prefix + edition decomposition**: for each alias that maps to a canonical, check if `name` matches `alias + " " + edition`. Handles "Ultra Europe" via alias "Ultra".
4. **No match**: return `(name, "")`.

### Resolution examples

| Input | Step | Result |
|---|---|---|
| "Tomorrowland Winter" | 2 (canonical + edition) | ("Tomorrowland", "Winter") |
| "Tomorrowland Belgium" | 2 (canonical + edition) | ("Tomorrowland", "Belgium") |
| "EDC Las Vegas" | 2 (canonical + edition) | ("EDC", "Las Vegas") |
| "Ultra Europe" | 3 (alias prefix + edition) | ("Ultra Music Festival", "Europe") |
| "Ultra Music Festival Miami" | 2 (canonical + edition) | ("Ultra Music Festival", "Miami") |
| "Tomorrowland Weekend 1" | 1 (alias) | ("Tomorrowland", "") |
| "TML" | 1 (alias) | ("Tomorrowland", "") |
| "AMF" | 1 (alias) | ("AMF", "") |
| "Red Rocks Amphitheatre" | 1 (alias) | ("Red Rocks", "") |
| "Unknown Fest" | 4 (no match) | ("Unknown Fest", "") |

### known_festivals expansion

Currently returns only canonical names. Expands to include alias keys, canonical values, and all `canonical + edition` combos. This ensures `_is_known_festival()` in the filename parser matches strings like "Tomorrowland Winter" and "EDC Las Vegas" in raw filenames.

### get_festival_display simplification

Remove `location_in_name` check. If the festival has an `editions` list and the provided edition matches one (case-insensitive), return `canonical + " " + edition`. Otherwise return just the canonical.

## Data Model Change

`MediaFile.location: str` becomes `MediaFile.edition: str`.

## Full File Change Map

### Core changes (behavioral)
- **config.py**: `all_known_editions`, `resolve_festival_with_edition()`, `get_festival_display(canonical, edition)`, expanded `known_festivals`
- **festivals.example.json**: `editions` key, cleaned aliases

### Mechanical renames (no behavioral change)
- **models.py**: field `edition: str = ""`
- **analyzer.py**: `info["edition"]`, calls to `resolve_festival_with_edition`
- **parsers.py**: `result["edition"]`, calls to `all_known_editions` and `resolve_festival_with_edition`
- **templates.py**: `media_file.edition`, `"edition"` in values dict
- **nfo.py**: `mf.edition`, "Edition" label in plot
- **operations.py**: `mf.edition` in poster and display calls
- **logging_util.py**: `"edition": mf.edition`

### Not changed
- embed_tags.py, chapters.py, api.py, source_cache.py, classifier.py, cli.py

### Tests
- test_config.py: rename methods, add edition decomposition tests
- test_parsers.py: `result["edition"]`, rename test functions
- test_templates.py: `edition=` in MediaFile construction
- test_nfo.py: `edition=` in MediaFile construction
- test_planner.py: `edition=` in MediaFile construction
- test_integration.py: `mf.edition` assertion

## Impact Analysis

### 1001TL chapter search: No impact
The search flow (CLI, API, chapter embedding) never touches editions, known_locations, or resolve_festival_with_location. It uses only the search query string and year.

### Filename parsing: Safe
The parser uses `_is_known_festival()` which does substring matching against `known_festivals`. The expanded property includes edition combos, so filenames like "Tomorrowland Winter 2026" and "EDC Las Vegas 2025" are still recognized. Raw text is stored in `result["edition"]` and resolved later by `resolve_festival_with_edition()` in the analyzer.

### WE1/WE2 handling: No change needed
"Tomorrowland Weekend 1" and "Weekend 2" stay as aliases (not editions). They resolve to "Tomorrowland" with no edition. The structured filename pattern (`YYYY - Festival - Artist - WE1`) already captures WE1/WE2 into `set_title` via a dedicated regex. The `CRATEDIGGER_1001TL_FESTIVAL` tag from 1001TL is always just "Tomorrowland" (no weekend), so no data is lost.

### Scan and organize commands: Indirect impact only
They call `analyse_file()` which calls `resolve_festival_with_edition()` and parsers which use `all_known_editions`. Then `render_folder()` / `render_filename()` call `get_festival_display()`. All mechanical renames, no behavioral change.

## No backward compatibility shim
No install base beyond dev instance. Clean break.
