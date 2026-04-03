# Display Artist: Preserve B2B/Collab Artists in Organize Pipeline

## Problem

`resolve_artist("Martin Garrix & Alesso")` returns `"Martin Garrix"`, making B2B sets
indistinguishable from solo sets in filenames. Two files at the same festival produce
identical filenames, causing one to be lost or collision-suffixed.

Additionally:
- Scan output only shows the target folder, not the full filename — hiding the artist stripping.
- Organize defaults to move, risking source data loss.

## Design

### New field: `display_artist` on MediaFile

The full multi-artist name, used for filenames and TITLE tags.

| Field | Derives from | Used for |
|-------|-------------|----------|
| `artist` | All layers -> `resolve_artist()` -> primary only | Folders, ARTIST tag (Plex grouping) |
| `display_artist` | 1001TL title -> filename parse (skip ARTIST tag) | Filenames, TITLE tag in MKV/NFO |

### Round-trip stability (no new MKV tag)

The full artist is already recoverable from existing sources:
- **1001TL-enriched files**: `CRATEDIGGER_1001TL_TITLE` survives round-trips, parsed at Layer 4.
- **Non-1001TL files**: The filename we write (e.g. `2025 - Red Rocks - Martin Garrix & Alesso.mkv`)
  is parsed back correctly on re-runs.

The ARTIST tag intentionally stores the primary-only artist for Plex grouping. The
`display_artist` derivation skips the ARTIST tag to avoid the stripped value overwriting
the full name.

### Separator normalization

Follow 1001TL convention: use `&`. Original `"B2B"` separators in filenames become `"&"`
after organize.

### Result

```
Martin Garrix/                                          # folder (primary artist)
  2025 - Red Rocks - Martin Garrix.mkv                  # solo set
  2025 - Red Rocks - Martin Garrix & Alesso.mkv         # B2B set, distinct
```

MKV tags:
- `ARTIST`: `Martin Garrix` (Plex groups under Garrix)
- `TITLE`: `Martin Garrix & Alesso @ Red Rocks, Red Rocks 2025`

## Code Changes

### 1. `models.py` — Add `display_artist` field

Add `display_artist: str = ""` to `MediaFile` dataclass.

### 2. `analyzer.py` — Build `display_artist` from pre-resolve artist

Derive `display_artist` using this priority (skip ARTIST tag):
1. 1001TL title parse (highest)
2. Filename parse
3. Parent directory (lowest)

Then normalize but do NOT run `resolve_artist()` on it.

Set `artist` as before (all layers including ARTIST tag, then `resolve_artist()`).

### 3. `templates.py` — Use `display_artist` in filename rendering

In `_build_values()`, use `display_artist` for the `"artist"` key in filename templates.
Folder templates continue using `artist` (primary only).

### 4. `embed_tags.py` + `nfo.py` — Use `display_artist` in TITLE construction

- ARTIST tag: keep `media_file.artist` (primary only, for Plex)
- TITLE tag: use `display_artist` in the `"artist @ stage, festival"` construction

### 5. `cli.py` + `progress.py` — Scan shows full target path

Show `-> folder/filename.mkv` instead of just `-> folder/`.

### 6. `cli.py` — Default to copy, make move opt-in

Swap the default: remove `--copy`, add `--move` flag. Organize copies by default.
