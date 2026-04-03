# Structured 1001TL Metadata: Stage, Venue, and Improved Posters

## Problem

The 1001TL title is stored as a flat comma-separated string (e.g. `"Armin van Buuren @ 25 Years Celebration Set, Area One, A State Of Trance Festival, Ahoy Rotterdam, Netherlands 2026-02-27"`). The parser tries to split this heuristically but can't distinguish set names from stages from venues. This causes:

1. **NFO `<title>` = artist name** for festival sets, duplicating `<artist>` — Kodi shows "Afrojack — Afrojack"
2. **Poster detail line overflows** — stage, set name, and venue all crammed into one fixed-size line
3. **No venue field** — venue data is lost or merged into stage

## Discovery

The 1001TL tracklist page `<h1>` has structured HTML that cleanly separates these concerns:

```html
<a href="/dj/...">Artist</a>
@ 25 Years Celebration Set, Area One,
<a href="/source/rch80m/...">A State Of Trance Festival</a>,
<a href="/source/tslp1m/...">Ahoy Rotterdam</a>,
Netherlands 2026-02-27
```

- **Plain text** between `@` and first `/source/` link = stage and/or set name
- **`/source/` links** = festivals, venues, parent events — each with a typed page

Each `/source/` page has a type label in `<div class="cRow"><div class="mtb5">`:
- `Open Air / Festival` → festival
- `Event Location` → venue
- `Conference` → parent event (e.g. Amsterdam Dance Event)

Also available: country from flag image `alt` attribute.

### Tested patterns (12 pages, 8 source pages)

| Set | Plain text (stage/set) | Sources | Venue (Event Location) |
|-----|----------------------|---------|----------------------|
| Afrojack EDC | kineticFIELD | EDC Las Vegas | — |
| Agents Of Time TML | Freedom Stage | Tomorrowland | — |
| Armin ASOT | 25 Years Celebration Set, Area One | ASOT Festival, Ahoy Rotterdam | Ahoy Rotterdam |
| Hardwell AMF | — | AMF, Johan Cruijff ArenA, ADE | Johan Cruijff ArenA Amsterdam |
| Hardwell TML | The Great Library Stage | Tomorrowland | — |
| HUGEL TML | Crystal Garden Stage | Tomorrowland | — |
| Maddix EDC | circuitGROUNDS | EDC Las Vegas | — |
| Martin Garrix Red Rocks | — | Red Rocks Amphitheatre | Red Rocks Amphitheatre |
| Oliver Heldens Mysteryland | Mainstage | Mysteryland | — |
| Showtek AMF | Hardstyle Exclusive | AMF, Johan Cruijff ArenA, ADE | Johan Cruijff ArenA Amsterdam |
| Tiesto ISOT EDC | In Search Of Sunrise, kineticFIELD | EDC Las Vegas | — |
| Marlon Hoffstadt AMF | — | AMF, ADE | — |

## Design

### 1. Parse `<h1>` in `export_tracklist()`

Replace the `<title>` tag extraction with `<h1>` parsing in `api.py`:
- Extract plain text between `@` and first `/source/` link → `stage_text`
- Extract `/source/` link IDs and slugs → list of `(id, slug, display_name)`

Add to `TracklistExport` dataclass:
- `stage_text: str` — raw plain text from h1 (e.g. "25 Years Celebration Set, Area One")
- `sources_by_type: dict[str, list[str]]` — source names grouped by type (e.g. `{"Event Location": ["Ahoy Rotterdam"], "Conference": ["Amsterdam Dance Event"]}`)

Keep `title` populated as before for backward compatibility.

### 2. Source cache (`~/.cratedigger/source_cache.json`)

Auto-populating cache keyed by source ID. Fetched once per unique source, reused forever.

```json
{
  "5tb5n3": {
    "name": "Amsterdam Music Festival",
    "slug": "amsterdam-music-festival",
    "type": "Open Air / Festival",
    "country": "Netherlands"
  },
  "tslp1m": {
    "name": "Ahoy Rotterdam",
    "slug": "ahoy-rotterdam",
    "type": "Event Location",
    "country": "Netherlands"
  }
}
```

Respects the existing `delay_seconds` config setting (default 5s, overridable via `--delay`) between source page fetches. Lives in `~/.cratedigger/source_cache.json` (user-level) because source types are global — not library-specific. Auto-created on first write. The `~/.cratedigger/` directory already exists for user config.

### 3. New MKV tags

| Tag | Source | Example |
|-----|--------|---------|
| `CRATEDIGGER_1001TL_STAGE` | Plain text from h1 | `25 Years Celebration Set, Area One` |
| `CRATEDIGGER_1001TL_FESTIVAL` | Sources with type `Open Air / Festival` | `A State Of Trance Festival` |
| `CRATEDIGGER_1001TL_VENUE` | Sources with type `Event Location` | `Ahoy Rotterdam` |
| `CRATEDIGGER_1001TL_CONFERENCE` | Sources with type `Conference` | `Amsterdam Dance Event` |
| `CRATEDIGGER_1001TL_RADIO` | Sources with type `Radio Channel` | `Insomniac Radio ONE` |

One tag per source type. Multiple sources of the same type are pipe-separated (e.g. `venue1|venue2`). Embedded alongside existing `CRATEDIGGER_1001TL_*` tags in `chapters.py` / `cli_handler.py`.

Source type to tag suffix mapping:

| Source page type | Tag suffix |
|-----------------|------------|
| `Open Air / Festival` | `FESTIVAL` |
| `Event Location` | `VENUE` |
| `Conference` | `CONFERENCE` |
| `Radio Channel` | `RADIO` |

Unknown types are logged but not stored as tags (added to mapping as encountered).

### 4. `MediaFile` model changes

New field:
- `venue: str = ""` — populated from `CRATEDIGGER_1001TL_VENUE` metadata tag

Existing `stage` field: populated from `CRATEDIGGER_1001TL_STAGE` when available (higher priority than the current heuristic parsing from the flat title).

### 5. `analyzer.py` changes

Read the new tags from MediaInfo metadata:
- `tracklists_stage` → `CRATEDIGGER_1001TL_STAGE`
- `tracklists_venue` → `CRATEDIGGER_1001TL_VENUE`

Layer 4 (1001TL overwrite) includes `stage` and populates `venue`.

### 6. NFO changes (`nfo.py`)

**Title for festival sets:**
```python
title = mf.stage or mf.artist or "Unknown Artist"
```

Results:
- `<title>kineticFIELD</title>` instead of `<title>Afrojack</title>`
- `<title>25 Years Celebration Set, Area One</title>` instead of `<title>Armin van Buuren</title>`

**Remove `<fileinfo>`/`<streamdetails>`:** Kodi overwrites this on playback per the wiki.

### 7. Poster changes (`poster.py`)

The set poster layout below the accent line becomes:

```
   FESTIVAL NAME                    ← bold, glow, auto-fit (existing)
   27 February 2026                 ← date (existing)
   25 Years Celebration Set         ← stage/set line 1 (split on comma)
   Area One                         ← stage/set line 2
   Ahoy Rotterdam                   ← venue line (new)
```

Changes:
- **Split stage on commas** into separate lines
- **Split venue on commas** into separate lines (if any)
- **Add `auto_fit`** to detail/venue lines to prevent overflow
- `detail` parameter: only `mf.stage`, no longer includes venue/location
- New `venue` parameter: `mf.venue`

### 8. Existing tag migration

Files already processed have `CRATEDIGGER_1001TL_TITLE` but no `_STAGE` or `_VENUE` tags. On next processing run, the h1 will be re-parsed (the tracklist page is already fetched for chapter export) and the new tags will be written alongside the existing ones.

## Out of scope

- Splitting the plain text into separate `set_title` vs `stage` fields — ambiguous with one segment (e.g. "Hardstyle Exclusive" is a set name, not a stage). Not needed for NFO title or poster display.
- `<actor>` tag in NFO — needs local artist thumb path, not just URL.
