# Tag Preservation, Search Fix & 1001TL Metadata — Design

**Date:** 2026-03-29
**Status:** Approved

## Problem

Three interconnected issues with MKV tag handling and 1001Tracklists chapter integration:

1. **Tags get destroyed**: Both `embed_tags.py` (ARTIST/TITLE/DATE at TTV=50) and `chapters.py` (1001TL URL/title at TTV=70) use `mkvpropedit --tags global:<file>`, which replaces ALL global tags. Whichever runs last destroys the other's tags.

2. **Chapter search broken**: The Python HTTP client returns zero results for queries that work on the 1001tracklists.com website with the same parameters. Root cause TBD (likely session/parsing issue).

3. **Credential config bug**: `_get_credentials()` reads from `config.tracklists_settings` but credentials live under `config.tracklists`.

## Design

### Part 1: Tag Preservation — Extract-Merge-Write

New module `festival_organizer/mkv_tags.py` with three functions:

- `extract_all_tags(filepath)` — `mkvextract` all tags into parsed XML element
- `merge_tags(existing, new_tags)` — Merge by TargetTypeValue scope; within same TTV, update/add by tag Name (new wins if non-empty, existing preserved if new is empty); unknown TTVs pass through unchanged
- `write_merged_tags(filepath, new_tags)` — Extract → merge → write via `mkvpropedit --tags global:<tmpfile>`

`new_tags` shape: `{50: {"ARTIST": "...", "TITLE": "..."}, 70: {"1001TRACKLISTS_URL": "..."}}`

**Callers updated:**
- `embed_tags.py`: Uses `write_merged_tags({50: {...}})` instead of building standalone XML
- `chapters.py`: Splits into two mkvpropedit calls — `--chapters` for chapters, `write_merged_tags({70: {...}})` for tags

### Part 2: Search Fix

1. Fix `_get_credentials()` to use `config.tracklists_credentials` (correct key)
2. Add debug logging: response status, content length, `bItm` class presence
3. Add fallback: if search returns 0 parsed results but response has content, retry without duration, then without year filter

### Part 3: Additional 1001TL Metadata

Embed additional tags at TTV=70 (data already available during chapter embedding):
- `1001TRACKLISTS_ID` — tracklist ID
- `1001TRACKLISTS_DATE` — performance date from search result

## Files Changed

| File | Change |
|------|--------|
| `festival_organizer/mkv_tags.py` | **NEW** — extract, merge, write utility |
| `festival_organizer/embed_tags.py` | Use `write_merged_tags()`, remove `_build_tag_xml()` |
| `festival_organizer/tracklists/chapters.py` | Use `write_merged_tags()`, refactor extraction, accept extra metadata |
| `festival_organizer/tracklists/cli_handler.py` | Fix credentials, pass extra metadata to `embed_chapters()` |
| `festival_organizer/tracklists/api.py` | Add debug logging to search |
| `festival_organizer/metadata.py` | Read new 1001TL tag names |

## Verification

1. Run `embed_tags` then `embed_chapters` on a test MKV — verify both TTV=50 and TTV=70 tags present via `mkvextract tags`
2. Run in reverse order — same result
3. Run each operation twice — no duplicate Simple elements
4. Run `cratedigger chapters` on AFROJACK test file — verify search returns results
5. Run existing tests
