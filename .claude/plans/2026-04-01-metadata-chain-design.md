# Clean Metadata Chain from 1001TL to Poster - Design Document

## Problem

`parse_1001tracklists_title()` tries to re-decompose a flat `<title>` string into festival/stage/edition/artist. It cannot distinguish venue from conference from country from edition, producing garbage `edition` values like `"Johan Cruijff ArenA, Amsterdam Dance Event, Netherlands"` that appear as unwanted second lines on festival album posters.

The root cause is structural: the chapters command already decomposes the `<h1>` into typed sources via the source_cache, but two source types are unmapped, artist DJ links are not extracted, and DJ profile data (aliases, groups) is not used.

## Context

### The `<h1>` is structured HTML

The 1001TL tracklist page has a structured `<h1>`:

```html
<a href="/dj/arminvanbuuren/">Armin van Buuren</a> &
<a href="/dj/kislashki/">KI/KI</a> @ Two Is One,
<a href="/source/5tb5n3/amsterdam-music-festival/">Amsterdam Music Festival</a>,
<a href="/source/hdfr2c/...">Johan Cruijff ArenA</a>,
<a href="/source/f4lzj3/...">Amsterdam Dance Event</a>,
Netherlands 2025-10-25
```

`_parse_h1_structure()` already decomposes the after-`@` part into typed sources via `/source/` links. Each source is looked up in the source_cache which knows its type and country.

The `<title>` tag is a lossy flat string of the same data. The title parser is a redundant, lossy reimplementation of what the `<h1>` parser already does correctly.

### Unmapped source types

`SOURCE_TYPE_TO_TAG` maps 3 of 5 source types:

| Source Type | Tag | Status |
|-------------|-----|--------|
| Open Air / Festival | CRATEDIGGER_1001TL_FESTIVAL | Mapped |
| Event Location | CRATEDIGGER_1001TL_VENUE | Mapped |
| Conference | CRATEDIGGER_1001TL_CONFERENCE | Mapped |
| Concert / Live Event | (none) | Dropped |
| Event Promoter | (none) | Dropped |

Examples of dropped sources:
- A State Of Trance Festival (Concert / Live Event) functions as festival
- We Belong Here (Event Promoter) functions as festival
- Resistance (Event Promoter) functions as stage context at Ultra

### DJ profile pages

Each `/dj/<slug>/` page has structured sections:

- **Aliases**: other names for the same person (Tiesto has VER:WEST, Allure; Alok has SOMETHING ELSE)
- **Member Of**: groups the DJ belongs to (Armin is member of Gaia; DVLM are members of 3 Are Legend)

Group pages have a **Group Members** section listing each member.

### Solo vs. collab in the `<h1>`

The `<h1>` encodes the distinction via `/dj/` links:

- Group (1 link): `<a href="/dj/dimitrivegasandlikemike/">Dimitri Vegas & Like Mike</a>`
- Collab (2 links): `<a href="/dj/arminvanbuuren/">Armin van Buuren</a> & <a href="/dj/kislashki/">KI/KI</a>`

## Changes

### Change 1: Extract DJ links from `<h1>`

Extend `_parse_h1_structure()` to extract `/dj/` links from before the `@`. Return as list of `(slug, display_name)` tuples.

Add to `TracklistExport`: `dj_artists: list[tuple[str, str]]`

Store as `CRATEDIGGER_1001TL_ARTISTS` tag, pipe-separated display names:
- Solo/group: `"Dimitri Vegas & Like Mike"` (1 DJ link, 1 entry)
- Collab: `"Armin van Buuren|KI/KI"` (2 DJ links, 2 entries)

In the analyzer, when this tag is present:
- 1 entry: use as both `artist` and `display_artist`
- 2+ entries: first entry becomes `artist` (folder routing), all entries joined with ` & ` becomes `display_artist`

Falls back to existing `resolve_artist()` + `artist_groups` logic for files without 1001TL data.

### Change 2: DJ cache with profile scraping

New `DjCache` (similar to `SourceCache`), keyed by DJ slug. When the chapters command encounters a DJ slug from the `<h1>`, fetch the `/dj/<slug>/` profile page and cache:

```json
{
  "arminvanbuuren": {
    "name": "Armin van Buuren",
    "aliases": [{"slug": "verwest", "name": "VER:WEST"}, {"slug": "allurenl", "name": "Allure"}],
    "member_of": [{"slug": "gaia-nl", "name": "Gaia"}]
  }
}
```

Parsed from the DJ profile page:
- `Aliases` section: `/dj/` links following the header
- `Member Of` section: `/dj/` links following the header

We already visit DJ pages for artwork (`_fetch_dj_artwork`), so the profile scraping piggybacks on that same request instead of making extra calls.

From this cache, dynamically derive:
- **Artist aliases**: `{VER:WEST: Tiesto, Allure: Tiesto, SOMETHING ELSE: Alok}`
- **Artist groups**: `{"gaia", "3 are legend", "logica"}`

These derived values merge with (and take priority over) the manually configured `artist_aliases` and `artist_groups` from `artists.json`. The manual config becomes a fallback/override for edge cases.

### Change 3: Promote unmapped source types

When `sources_by_type` has no `"Open Air / Festival"`, promote the first available from (in priority order):

1. `"Concert / Live Event"` (e.g., A State Of Trance Festival)
2. `"Event Promoter"` (e.g., We Belong Here)

Promoted source gets written as `CRATEDIGGER_1001TL_FESTIVAL`.

Rule: only promote when there is no existing `"Open Air / Festival"`. When one exists (e.g., Ultra Music Festival Miami), "Event Promoter" (Resistance) stays in its own type and is not promoted.

### Change 4: Remove `parse_1001tracklists_title()`

With all data covered by dedicated tags, this function is removed:

| Data | Dedicated Source |
|------|-----------------|
| artist | `CRATEDIGGER_1001TL_ARTISTS` (new) |
| festival | `CRATEDIGGER_1001TL_FESTIVAL` (now always present via promotion) |
| stage | `CRATEDIGGER_1001TL_STAGE` |
| date | `CRATEDIGGER_1001TL_DATE` |
| edition | `resolve_festival_with_edition()` on the festival tag |
| venue | `CRATEDIGGER_1001TL_VENUE` |

Remove the function and its call in the analyzer (Layer 4 title parsing).

### Change 5: Fix config.json trailing comma

Line 136 trailing comma makes the entire config fail to parse silently.

## Files Changed

| File | Change |
|------|--------|
| `tracklists/api.py` | Extract DJ links from `<h1>` before `@`; scrape aliases/groups from DJ profile pages (piggyback on artwork fetch) |
| `tracklists/dj_cache.py` | New file: `DjCache` class, stores slug/name/aliases/member_of per DJ |
| `tracklists/cli_handler.py` | Write `CRATEDIGGER_1001TL_ARTISTS` tag; promote unmapped source types |
| `tracklists/chapters.py` | Accept and write artists tag |
| `tracklists/source_cache.py` | Promotion logic for unmapped source types |
| `metadata.py` | Read `CRATEDIGGER_1001TL_ARTISTS` tag |
| `analyzer.py` | Use artists tag for artist/display_artist; remove Layer 4 title parsing |
| `config.py` | Merge DJ cache aliases/groups with manual config |
| `parsers.py` | Remove `parse_1001tracklists_title()` |
| `tests/test_parsers.py` | Remove title parser tests |
| `config.json` | Fix trailing comma |

## What Stays Unchanged

- `_parse_h1_structure` source extraction (extended, not replaced)
- `resolve_artist()` split logic (fallback for non-1001TL files)
- `parse_filename()` (still needed for files without 1001TL tags)
- Poster code, NFO, templates (all consumers of MediaFile fields)
- `resolve_festival_with_edition()` in analyzer Layer 5
- `SourceCache` structure (unchanged, consulted for promotion)

## Verification

- All existing tests pass (minus removed title parser tests)
- For all 71 files in test data: confirm `edition` is empty unless a real known edition is present
- DVLM files: single `artist` entry, no split
- Armin & KI/KI files: two entries, first used for folder routing
- ASOT and WBH files: get `CRATEDIGGER_1001TL_FESTIVAL` via promotion
- VER:WEST tracklist: resolves to Tiesto folder via DJ cache alias
- DJ cache populated with aliases/groups for all encountered DJs
