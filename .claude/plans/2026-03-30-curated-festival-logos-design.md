# Curated Festival Logos — Implementation Plan

## Context

1001Tracklists event artwork is unreliable — often returns artist profile images or Apple Music covers instead of actual festival logos (e.g., ALOK's Tomorrowland Brasil set got a random Soundcloud avatar). We're replacing the 1001TL event artwork system with user-curated festival logos stored in a designated folder, giving users full control over image quality.

## Design Decisions (validated through prototype testing)

- **Folder convention:** `.cratedigger/festivals/{CanonicalName}/logo.{jpg,png,webp}` — subdirectory per festival
- **Two-level lookup:** Library-level first, then `~/.cratedigger/festivals/` fallback
- **Name matching:** Canonical festival name via existing `resolve_festival_alias()`
- **Supported formats:** jpg, png, webp (no SVG — Pillow limitation)
- **Transparency support:** RGBA logos composite cleanly over gradient backgrounds
- **Priority chains:**
  - Festival: `curated_logo` → `thumb_collage` → `gradient`
  - Artist: `dj_artwork` → `fanart_tv` → `gradient`
  - Year: `gradient` (unchanged)
- **Reporting:** End-of-run summary + standalone `audit-logos` command
- **Cleanup:** Remove all 1001TL event artwork scraping/tagging code; existing tags in files untouched

## Steps

### Step 1: Poster rendering — RGBA throughout + gradient-first for album posters

Work in RGBA throughout the entire poster pipeline. Both `generate_set_poster()` and `generate_album_poster()` should keep images as RGBA during compositing and only flatten to RGB at final save. This is simpler than special-casing per poster type and handles any transparent source gracefully.

**For album posters specifically:** refactor all 3 rendering paths to start with a gradient base layer. Logos (including transparent PNGs) are composited on top, letting the gradient show through transparent areas.

**Gradient base color derivation chain (album posters):**
1. Sample visible (non-transparent) pixels from the background image → average RGB
2. If luminance < 30 (too dark, e.g., black TML logo), fall back to `get_dominant_color_from_thumbs(thumb_paths)` — derives color from video thumbnails (stage lighting etc.)
3. Last resort: neutral dark `(40, 40, 50)`

**The 3 album poster paths, all starting from gradient:**
- **Small + festival:** gradient → ratio-preserving tile overlay → centered sharp RGBA logo
- **Small + artist:** gradient → blurred overlay at ~60% opacity → centered sharp RGBA logo
- **Large:** gradient → sharp-top-fade with RGBA alpha compositing

**Files:** `festival_organizer/poster.py` — both `generate_set_poster()` (line 272) and `generate_album_poster()` (line 650)

### Step 2: Poster rendering — ratio-preserving tiles

Change tile generation from square-crop to aspect-ratio-preserving. Currently tiles center-crop to square (`sq = min(w, h)`), which chops off parts of wide/tall logos.

**Fix:** Scale the logo to fit within `tile_max` (200px on longest side), preserving aspect ratio. Tile the grid with these non-square cells.

Applies to all tile paths in `poster.py` (album poster festival layout) and any other tile usage.

**File:** `festival_organizer/poster.py`

### Step 3: Poster rendering — remove edge fade from centered image mask

Change `_rounded_edge_mask()` to only use rounded corners, removing the 25px soft edge fade. Tested and confirmed cleaner results — the fade added unnecessary blurriness, especially for transparent logos that already have their own alpha edges.

**Before:** rounded corners + 25px inward fade + blur
**After:** rounded corners + light blur only

This affects all centered sharp images in small-source paths (both festival tile+center and artist blur+center).

**File:** `festival_organizer/poster.py` (`_rounded_edge_mask()` at line 474)

### Step 4: Add `_find_curated_logo()` to operations.py

New method on `AlbumPosterOperation`:

```python
def _find_curated_logo(self, folder: Path, festival: str) -> Path | None:
    canonical = self.config.resolve_festival_alias(festival) if festival else ""
    if not canonical:
        return None
    search_dirs = []
    if self.library_root:
        search_dirs.append(self.library_root / ".cratedigger" / "festivals" / canonical)
    search_dirs.append(Path.home() / ".cratedigger" / "festivals" / canonical)
    for d in search_dirs:
        for ext in ("jpg", "jpeg", "png", "webp"):
            candidate = d / f"logo.{ext}"
            if candidate.exists():
                logger.info("Curated logo: %s", candidate)
                return candidate
    return None
```

Register `"curated_logo"` in `_try_background_source()`.

**File:** `festival_organizer/operations.py`

### Step 5: Update default priority chains in config.py

```python
"poster_settings": {
    "artist_background_priority": ["dj_artwork", "fanart_tv", "gradient"],
    "festival_background_priority": ["curated_logo", "thumb_collage", "gradient"],
    "year_background_priority": ["gradient"],
},
```

**File:** `festival_organizer/config.py` (lines 136-140)

### Step 6: Remove 1001TL event artwork scraping

- **`tracklists/api.py`**: Remove `_extract_event_artwork()` (lines 372-391) and its call in `export_tracklist()`
- **`tracklists/chapters.py`**: Remove `event_artwork_url` parameter from `embed_chapters()` and the tag write
- **`tracklists/cli_handler.py`**: Remove `event_artwork_url=export.event_artwork_url` from `embed_chapters()` call
- **`models.py`**: Remove `event_artwork_url` field from `MediaFile`
- **`metadata.py`**: Remove `tracklists_event_artwork` extraction (lines 138-142)
- **`operations.py`**: Remove `_find_event_artwork()` (lines 325-333) and `"event_artwork"` case from `_try_background_source()`

### Step 7: Add end-of-run logo summary reporting

In `AlbumPosterOperation`, track which festivals used curated logos, which fell back, and print a summary via `ProgressPrinter` at the end.

Also check for unmatched folders in `.cratedigger/festivals/` (typos, stale entries).

**Files:** `festival_organizer/operations.py`, `festival_organizer/progress.py`

### Step 8: Add `audit-logos` CLI command

```
cratedigger audit-logos [library_path]
```

Scans the library for all canonical festival names found in media files, cross-references with `.cratedigger/festivals/` directories, and reports:
- Festivals with curated logos
- Festivals missing logos (with suggested folder name)
- Unmatched folders (possible typos)
- Unsupported file formats found (e.g., .svg)

**Files:** `festival_organizer/cli.py`, new function in `festival_organizer/operations.py` or small `audit.py`

### Step 9: Update tests

- Update tests for `_try_background_source` → new `curated_logo` source
- Update tests for `embed_chapters` → removed `event_artwork_url` param
- Update tests for `export_tracklist` → no longer returns event artwork
- Add tests for `_find_curated_logo()` (library-level, user-level, missing)
- Add tests for `audit-logos` command
- Add tests for RGBA compositing in poster generation
- Add tests for ratio-preserving tile generation

**Files:** `tests/` directory

## Verification

1. Copy test logos from `/home/user/_temp/cratedigger/festivals/` into library `.cratedigger/festivals/{CanonicalName}/logo.*` structure
2. Use thumbnails from `/home/user/_temp/cratedigger/thumbs/` for color fallback testing
3. Run `cratedigger enrich` — verify curated logos are picked up, gradient colors correct for dark logos
4. Run `cratedigger audit-logos` — verify all festivals listed with logo status
5. Verify end-of-run summary shows logo hits/misses
6. Run existing test suite — all tests pass
7. Run `cratedigger chapters` — verify no event artwork scraping/tagging
8. Visual check: compare generated posters against test output in `/home/user/_temp/cratedigger/test_output_layered/`

## Key Files

| File | Changes |
|------|---------|
| `festival_organizer/poster.py` | Gradient-first layered approach, RGBA compositing, ratio tiles, remove edge fade |
| `festival_organizer/operations.py` | Add `_find_curated_logo()`, remove `_find_event_artwork()`, update `_try_background_source()`, logo tracking/summary |
| `festival_organizer/config.py` | Update default priority chains |
| `festival_organizer/tracklists/api.py` | Remove `_extract_event_artwork()` |
| `festival_organizer/tracklists/chapters.py` | Remove `event_artwork_url` param |
| `festival_organizer/tracklists/cli_handler.py` | Remove event artwork passing |
| `festival_organizer/models.py` | Remove `event_artwork_url` field |
| `festival_organizer/metadata.py` | Remove event artwork extraction |
| `festival_organizer/cli.py` | Add `audit-logos` subcommand |
