# Tag reference

CrateDigger writes structured metadata into each MKV using Matroska tags. Tags are grouped by `TargetTypeValue` (TTV), which scopes the tag to a level in the release model:

| TTV | Scope | Meaning |
|----:|-------|---------|
| 50 | File | Single-file display metadata (ARTIST, TITLE, DATE). What Kodi/Plex/Jellyfin show for the file. |
| 70 | Collection | File-level enrichment metadata in the `CRATEDIGGER_*` namespace (MBIDs, 1001TL identifiers, fanart URLs). Also the place for album-level multi-artist tags. |
| 30 | Chapter | Per-chapter track metadata (PERFORMER, TITLE, LABEL, GENRE, MBIDs). Surfaced by `ffprobe -show_chapters` for downstream tools like TrackSplit. |

This page lists every tag CrateDigger writes, which command produces it, and how consumers can read it.

## File-level (TTV=50)

Written by `enrich` via `TagsOperation` unless noted otherwise. These are the tags any generic MKV-aware media server reads and displays.

| Tag | Written by | Content | Example |
|-----|------------|---------|---------|
| `ARTIST` | enrich / TagsOperation | Primary DJ only (from `media_file.artist`, post alias resolution). Used for folder routing and single-value consumers. | `Armin van Buuren` |
| `TITLE` | enrich / TagsOperation | Display title from `build_display_title`: for festival sets, `Artist @ Stage, Festival`; otherwise the concert/show title. | `Armin van Buuren & KI/KI @ Two Is One, Amsterdam Music Festival` |
| `DATE_RELEASED` | enrich / TagsOperation | Release date or year. | `2025-10-25` |
| `SYNOPSIS` | enrich / TagsOperation | Curated multi-line description: `artist @ stage`, `festival (source), country`, `Edition: ...`. | (3 lines) |
| `DESCRIPTION` | enrich / TagsOperation | Cleared to empty so yt-dlp's default description is removed. | `` |

## Collection-level (TTV=70)

The `CRATEDIGGER_*` namespace carries enrichment identifiers and multi-value artist tags. All written at collection scope so consumers that ignore per-chapter tags still see them.

### Identifiers and URLs

Written by `identify` (1001TL-sourced) or `enrich / TagsOperation` (MBID, fanart URLs).

| Tag | Written by | Content | Example |
|-----|------------|---------|---------|
| `CRATEDIGGER_1001TL_URL` | identify / embed_chapters | Permalink to the 1001Tracklists page. | `https://www.1001tracklists.com/tracklist/...` |
| `CRATEDIGGER_1001TL_TITLE` | identify / embed_chapters | Tracklist title as shown on 1001TL. | `Armin van Buuren & KI/KI @ Two Is One, ADE 2025` |
| `CRATEDIGGER_1001TL_ID` | identify / embed_chapters | Numeric tracklist ID. | `1hv3n1nt` |
| `CRATEDIGGER_1001TL_DATE` | identify / embed_chapters | Event date from 1001TL. | `2025-10-25` |
| `CRATEDIGGER_1001TL_GENRES` | identify / embed_chapters | Top 5 most frequent per-track genres, pipe-separated. | `Big Room\|Tech House\|Techno` |
| `CRATEDIGGER_1001TL_DJ_ARTWORK` | identify / embed_chapters | URL to the DJ photo on the 1001TL page. | `https://...` |
| `CRATEDIGGER_1001TL_STAGE` | identify / embed_chapters | Stage name if one is listed. | `Two Is One` |
| `CRATEDIGGER_1001TL_FESTIVAL` | identify / embed_chapters | Source display name when the tracklist is tagged as a festival. | `Amsterdam Music Festival` |
| `CRATEDIGGER_1001TL_VENUE` | identify / embed_chapters | Venue display name. | `Johan Cruijff ArenA` |
| `CRATEDIGGER_1001TL_EVENT` | identify / embed_chapters | Event/conference display name. | `Amsterdam Dance Event` |
| `CRATEDIGGER_1001TL_COUNTRY` | identify / embed_chapters | Country of the event. | `Netherlands` |
| `CRATEDIGGER_1001TL_SOURCE_TYPE` | identify / embed_chapters | Priority-ranked source category: Open Air / Festival > Event Location > Conference > ... | `Open Air / Festival` |
| `CRATEDIGGER_FANART_URL` | enrich / TagsOperation | URL of the artist background downloaded from fanart.tv. | `https://...` |
| `CRATEDIGGER_CLEARLOGO_URL` | enrich / TagsOperation | URL of the artist clear logo from fanart.tv. | `https://...` |
| `CRATEDIGGER_ENRICHED_AT` | enrich / TagsOperation | ISO-8601 timestamp of the most recent enrich pass that wrote TTV=70 tags. | `2026-04-14T10:15:30+00:00` |

### Album-level artist tags

Written at identify time (names / display / slugs) and enrich time (MBIDs). These mirror the per-chapter multi-artist pattern at the album level so downstream taggers can produce a proper multi-value `ALBUMARTIST` credit.

| Tag | Written by | Content | Example |
|-----|------------|---------|---------|
| `CRATEDIGGER_1001TL_ARTISTS` | identify / embed_chapters | Pipe-separated canonical DJ names, post `DjCache.canonical_name` so 1001TL ALL-CAPS submissions are normalized. | `Armin van Buuren\|KI/KI` |
| `CRATEDIGGER_ALBUMARTIST_SLUGS` | identify / embed_chapters | Pipe-separated 1001TL DJ slugs, positionally aligned with `CRATEDIGGER_1001TL_ARTISTS`. | `arminvanbuuren\|kislashki` |
| `CRATEDIGGER_ALBUMARTIST_DISPLAY` | identify / embed_chapters | Human-readable `" & "` join of canonical names. Sibling to `TITLE`; what taggers should use as the `ALBUMARTIST` display string. | `Armin van Buuren & KI/KI` |
| `CRATEDIGGER_ALBUMARTIST_MBIDS` | enrich / AlbumArtistMbidsOperation | Pipe-separated MusicBrainz artist IDs, positionally aligned with `CRATEDIGGER_1001TL_ARTISTS`; empty slot `""` for unresolved names. | `477b8c0c-c5fc-4ad2-b5b2-191f0bf2a9df\|<kiki-mbid>` |

## Per-chapter (TTV=30)

Written by identify via `embed_chapters` → `_build_chapter_tags_map`, except `MUSICBRAINZ_ARTISTIDS` which is written by enrich. Surface directly in `ffprobe -show_chapters`.

| Tag | Written by | Content | Example |
|-----|------------|---------|---------|
| `PERFORMER` | identify / embed_chapters | Primary artist display name of the track, alias-resolved. Preserves original casing. | `deadmau5` |
| `PERFORMER_SLUGS` | identify / embed_chapters | Pipe-separated 1001TL slugs for every artist linked on the row. | `afrojack\|oliver-heldens` |
| `PERFORMER_NAMES` | identify / embed_chapters | Pipe-separated display names for every artist, aligned with `PERFORMER_SLUGS`. | `Afrojack\|Oliver Heldens` |
| `MUSICBRAINZ_ARTISTIDS` | enrich / ChapterArtistMbidsOperation | Pipe-separated MusicBrainz artist IDs, aligned with `PERFORMER_NAMES`; empty slot `""` for unresolved names. | `<afrojack-mbid>\|<heldens-mbid>` |
| `TITLE` | identify / embed_chapters | Clean track title with the artist prefix stripped. | `Take Over Control` |
| `LABEL` | identify / embed_chapters | Record label as plain text. | `WALL` |
| `GENRE` | identify / embed_chapters | Pipe-separated per-track genres. | `Big Room\|Electro House` |

## Alignment invariants

Two tag families rely on positional alignment across pipe-separated values. Downstream consumers (TrackSplit → Lyrion/Jellyfin, or any custom tagger) can zip them by index to produce multi-value credits with MBIDs attached.

**Per-chapter**:

```
len(PERFORMER_SLUGS.split("|")) == len(PERFORMER_NAMES.split("|")) == len(MUSICBRAINZ_ARTISTIDS.split("|"))
```

**Album-level**:

```
len(CRATEDIGGER_1001TL_ARTISTS.split("|")) == len(CRATEDIGGER_ALBUMARTIST_SLUGS.split("|")) == len(CRATEDIGGER_ALBUMARTIST_MBIDS.split("|"))
```

`CRATEDIGGER_ALBUMARTIST_DISPLAY` is the human-readable sibling of the three album-level list tags and is not pipe-separated.

Unresolved MBIDs are preserved as empty slots (`""`), never dropped. This keeps the zip invariant intact even when MusicBrainz search misses or the override file is incomplete.

## Worked example: Armin van Buuren b2b KI/KI

For the set "Armin van Buuren & KI/KI @ Amsterdam Music Festival 2025" (a B2B with two DJs):

### After `cratedigger identify`

```
CRATEDIGGER_1001TL_URL=https://www.1001tracklists.com/tracklist/.../...
CRATEDIGGER_1001TL_TITLE=Armin van Buuren & KI/KI @ Two Is One, AMF 2025
CRATEDIGGER_1001TL_ARTISTS=Armin van Buuren|KI/KI
CRATEDIGGER_ALBUMARTIST_SLUGS=arminvanbuuren|kislashki
CRATEDIGGER_ALBUMARTIST_DISPLAY=Armin van Buuren & KI/KI
# per-chapter (TTV=30) tags on each ChapterUID:
#   PERFORMER, PERFORMER_SLUGS, PERFORMER_NAMES, TITLE, LABEL, GENRE
```

### After `cratedigger enrich`

```
# File-level (TTV=50) added/updated:
ARTIST=Armin van Buuren                # primary DJ only (folder routing, single-value fallback)
TITLE=Armin van Buuren & KI/KI @ Two Is One, Amsterdam Music Festival
DATE_RELEASED=2025-10-25
SYNOPSIS=...

# Collection-level (TTV=70) added:
CRATEDIGGER_FANART_URL=https://assets.fanart.tv/...
CRATEDIGGER_CLEARLOGO_URL=https://assets.fanart.tv/...
CRATEDIGGER_ALBUMARTIST_MBIDS=477b8c0c-c5fc-4ad2-b5b2-191f0bf2a9df|<kiki-mbid-or-empty>
CRATEDIGGER_ENRICHED_AT=2026-04-14T10:15:30+00:00

# Per-chapter (TTV=30) updated with:
#   MUSICBRAINZ_ARTISTIDS (aligned with PERFORMER_NAMES)
```

When KI/KI's MBID is not yet in the MBID cache and MusicBrainz search misses, the corresponding slots in `CRATEDIGGER_ALBUMARTIST_MBIDS` and per-chapter `MUSICBRAINZ_ARTISTIDS` are empty strings (`477b8c0c-...|`). Adding KI/KI to `~/.cratedigger/artist_mbids.json` and re-running `enrich --only chapter_artist_mbids,album_artist_mbids --regenerate` fills those slots.

## See also

- [Enrich / Chapter artist MBIDs](commands/enrich.md#chapter-artist-mbids-chapter_artist_mbids) — per-chapter MBID resolution, override file, fix loop.
- [Enrich / Album-artist MBIDs](commands/enrich.md#album-artist-mbids-album_artist_mbids) — album-level MBID resolution.
- [1001Tracklists](tracklists.md) — how identify extracts per-chapter metadata.
- [artist_mbids.json override file](configuration.md#artist-mbid-override-file) — user-curated MBID overrides (shared by both MBID operations).
- [Kodi Integration](kodi-integration.md) — how these tags surface in Kodi display.
