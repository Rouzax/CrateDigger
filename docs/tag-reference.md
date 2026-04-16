# Tag reference

CrateDigger writes structured metadata into each MKV file using Matroska tags. Tags are grouped by scope level (called `TargetTypeValue` or TTV), which determines what the tag applies to:

| TTV | Scope | Used for |
|----:|-------|---------|
| 50 | File | Display metadata that any media player reads: artist, title, date |
| 70 | Collection | CrateDigger enrichment data: 1001Tracklists identifiers, fanart URLs, album-level artist credits |
| 30 | Chapter | Per-track metadata: performer, title, label, genre, MusicBrainz IDs |

## How the commands divide tag responsibility

The three-step workflow maps cleanly onto the three tag scopes:

- **`identify`** writes TTV=70 and TTV=30. It embeds everything downstream needs: the 1001Tracklists identifiers, album-level artist names and slugs, and per-chapter performer names, track titles, labels, and genres. `organize` reads these tags to build folder and file names.

- **`enrich`** writes TTV=50. It reads the rich metadata that `identify` embedded, resolves aliases, and produces the clean display-layer tags (ARTIST, TITLE, DATE_RELEASED, SYNOPSIS) that media players and NFO consumers use. It also resolves MusicBrainz IDs and writes them positionally aligned with the slugs and names `identify` already placed.

This is why the order matters: `enrich` depends on what `identify` wrote.

---

## File-level tags (TTV=50)

Written by `enrich` (`tags` operation). These are the tags any MKV-aware media player reads and displays.

| Tag | Content | Example |
|-----|---------|---------|
| `ARTIST` | Primary artist only, after alias resolution. Used for folder routing and single-value consumers. | `Armin van Buuren` |
| `TITLE` | Display title. For festival sets: `Artist @ Stage, Festival`. For concerts: the concert title. | `Armin van Buuren & KIKI @ Two Is One, AMF` |
| `DATE_RELEASED` | Event date or year. | `2025-10-25` |
| `SYNOPSIS` | Generated description: artist and stage, then festival (falling back to venue, then freeform location) with country, then edition and set title. Only lines with data are included. | (multi-line) |
| `DESCRIPTION` | Cleared to empty. Removes the auto-generated description yt-dlp embeds from the YouTube page. | `` |

---

## Collection-level tags (TTV=70)

The `CRATEDIGGER_*` namespace carries enrichment identifiers and multi-value artist data. Written at collection scope so consumers that ignore per-chapter tags still see them.

### 1001Tracklists identifiers

Written by `identify`.

| Tag | Content | Example |
|-----|---------|---------|
| `CRATEDIGGER_1001TL_URL` | Permalink to the 1001Tracklists tracklist page | `https://www.1001tracklists.com/tracklist/...` |
| `CRATEDIGGER_1001TL_TITLE` | Tracklist title as shown on 1001Tracklists | `Armin van Buuren & KIKI @ Two Is One, AMF 2025` |
| `CRATEDIGGER_1001TL_ID` | Numeric tracklist ID | `1hv3n1nt` |
| `CRATEDIGGER_1001TL_DATE` | Event date from 1001Tracklists | `2025-10-25` |
| `CRATEDIGGER_1001TL_GENRES` | Top 5 most frequent per-track genres, pipe-separated | `Techno\|Trance\|Hard Dance` |
| `CRATEDIGGER_1001TL_DJ_ARTWORK` | URL to the DJ photo on the tracklist page | `https://...` |
| `CRATEDIGGER_1001TL_STAGE` | Stage name if listed | `Two Is One` |
| `CRATEDIGGER_1001TL_FESTIVAL` | Festival display name when the source is a festival | `Amsterdam Music Festival` |
| `CRATEDIGGER_1001TL_VENUE` | Venue display name | `Johan Cruijff ArenA` |
| `CRATEDIGGER_1001TL_EVENT` | Event or conference display name | `Amsterdam Dance Event` |
| `CRATEDIGGER_1001TL_COUNTRY` | Country of the event | `Netherlands` |
| `CRATEDIGGER_1001TL_LOCATION` | Freeform location text from the tracklist header, written only when no linked festival/venue/conference/radio source is present | `Alexandra Palace London` |
| `CRATEDIGGER_1001TL_SOURCE_TYPE` | Source category: Open Air / Festival, Event Location, Conference, etc. | `Open Air / Festival` |

### Fanart URLs

Written by `enrich` (`tags` operation).

| Tag | Content | Example |
|-----|---------|---------|
| `CRATEDIGGER_FANART_URL` | URL of the artist background image downloaded from fanart.tv | `https://assets.fanart.tv/...` |
| `CRATEDIGGER_CLEARLOGO_URL` | URL of the artist clear logo from fanart.tv | `https://assets.fanart.tv/...` |
| `CRATEDIGGER_ENRICHED_AT` | Timestamp of the most recent enrich pass that wrote collection-level tags | `2026-04-14T10:15:30+00:00` |

### Album-level artist tags

Written by `identify` (names, display, slugs) and `enrich` (`album_artist_mbids` operation for MBIDs). These mirror the per-chapter multi-artist pattern at the album level for downstream tools that need a full multi-value artist credit.

| Tag | Written by | Content | Example |
|-----|-----------|---------|---------|
| `CRATEDIGGER_1001TL_ARTISTS` | identify | Pipe-separated canonical DJ names, normalized from 1001Tracklists | `Armin van Buuren\|KIKI` |
| `CRATEDIGGER_ALBUMARTIST_SLUGS` | identify | Pipe-separated 1001Tracklists DJ slugs, positionally aligned with `CRATEDIGGER_1001TL_ARTISTS` | `arminvanbuuren\|kislashki` |
| `CRATEDIGGER_ALBUMARTIST_DISPLAY` | identify | Human-readable join of all artist names. The value to use as a display `ALBUMARTIST`. | `Armin van Buuren & KIKI` |
| `CRATEDIGGER_ALBUMARTIST_MBIDS` | enrich | Pipe-separated MusicBrainz artist IDs, positionally aligned with `CRATEDIGGER_1001TL_ARTISTS`. Empty slot `""` for unresolved names. | `477b8c0c-...\|<kiki-mbid>` |

---

## Per-chapter tags (TTV=30)

Written by `identify`, except `MUSICBRAINZ_ARTISTIDS` which is written by `enrich` (`chapter_artist_mbids` operation). These tags are attached to each chapter (track) in the MKV.

| Tag | Written by | Content | Example |
|-----|-----------|---------|---------|
| `CRATEDIGGER_TRACK_PERFORMER` | identify | Primary artist display name of the track, exactly as 1001Tracklists renders it | `AFROJACK ft. Eva Simons` |
| `CRATEDIGGER_TRACK_PERFORMER_SLUGS` | identify | Pipe-separated 1001Tracklists slugs for every artist on the track | `afrojack\|oliver-heldens` |
| `CRATEDIGGER_TRACK_PERFORMER_NAMES` | identify | Pipe-separated display names for every artist, aligned with `CRATEDIGGER_TRACK_PERFORMER_SLUGS` | `Afrojack\|Oliver Heldens` |
| `MUSICBRAINZ_ARTISTIDS` | enrich | Pipe-separated MusicBrainz artist IDs, aligned with `CRATEDIGGER_TRACK_PERFORMER_NAMES`. Empty slot `""` for unresolved names. | `<afrojack-mbid>\|<heldens-mbid>` |
| `TITLE` | identify | Track title with the artist prefix stripped | `Take Over Control` |
| `CRATEDIGGER_TRACK_LABEL` | identify | Record label | `WALL` |
| `CRATEDIGGER_TRACK_GENRE` | identify | Pipe-separated per-track genres | `Big Room\|Electro House` |

The `CRATEDIGGER_TRACK_*` prefix is deliberate: it keeps these per-chapter tags out of mediainfo's flattened "General" section. Unprefixed standard Matroska names (`PERFORMER`, `LABEL`, `GENRE`) at TTV=30 get promoted into mediainfo's file-level display (last chapter wins), making files look like they carry the last chapter's values at file scope. The prefix avoids that without changing playback behaviour in Matroska-aware readers (Kodi uses the chapter's `ChapterString` for the title, not these tags).

---

## Pipe alignment

Two tag families use pipe-separated values that are positionally aligned. You can zip them by index to produce multi-value credits with MBIDs attached.

**Per-chapter:**

```
CRATEDIGGER_TRACK_PERFORMER_SLUGS  |  CRATEDIGGER_TRACK_PERFORMER_NAMES  |  MUSICBRAINZ_ARTISTIDS
              slot 0                |               slot 0                 |         slot 0
              slot 1                |               slot 1                 |         slot 1
```

**Album-level:**

```
CRATEDIGGER_1001TL_ARTISTS  |  CRATEDIGGER_ALBUMARTIST_SLUGS  |  CRATEDIGGER_ALBUMARTIST_MBIDS
          slot 0             |              slot 0              |              slot 0
          slot 1             |              slot 1              |              slot 1
```

`CRATEDIGGER_ALBUMARTIST_DISPLAY` is the human-readable version of the album-level list and is not pipe-separated.

Unresolved MBIDs are preserved as empty slots (`""`), never dropped. This keeps the alignment intact even when a MusicBrainz lookup fails.

---

## Worked example: Armin van Buuren b2b KIKI at AMF 2025

### After `identify`

```
CRATEDIGGER_1001TL_URL=https://www.1001tracklists.com/tracklist/...
CRATEDIGGER_1001TL_TITLE=Armin van Buuren & KIKI @ Two Is One, AMF 2025
CRATEDIGGER_1001TL_ARTISTS=Armin van Buuren|KIKI
CRATEDIGGER_ALBUMARTIST_SLUGS=arminvanbuuren|kislashki
CRATEDIGGER_ALBUMARTIST_DISPLAY=Armin van Buuren & KIKI

# Per chapter (TTV=30):
#   CRATEDIGGER_TRACK_PERFORMER, CRATEDIGGER_TRACK_PERFORMER_SLUGS,
#   CRATEDIGGER_TRACK_PERFORMER_NAMES, TITLE,
#   CRATEDIGGER_TRACK_LABEL, CRATEDIGGER_TRACK_GENRE
```

### After `enrich`

```
# File-level (TTV=50):
ARTIST=Armin van Buuren
TITLE=Armin van Buuren & KIKI @ Two Is One, AMF
DATE_RELEASED=2025-10-25
SYNOPSIS=...

# Collection-level (TTV=70) additions:
CRATEDIGGER_FANART_URL=https://assets.fanart.tv/...
CRATEDIGGER_CLEARLOGO_URL=https://assets.fanart.tv/...
CRATEDIGGER_ALBUMARTIST_MBIDS=477b8c0c-c5fc-4ad2-b5b2-191f0bf2a9df|<kiki-mbid-or-empty>
CRATEDIGGER_ENRICHED_AT=2026-04-14T10:15:30+00:00

# Per chapter (TTV=30) additions:
#   MUSICBRAINZ_ARTISTIDS (aligned with CRATEDIGGER_TRACK_PERFORMER_NAMES)
```

If KIKI's MBID is not yet in the cache, her slot in `CRATEDIGGER_ALBUMARTIST_MBIDS` and the per-chapter `MUSICBRAINZ_ARTISTIDS` will be an empty string. Add her to `~/.cratedigger/artist_mbids.json` and re-run:

```bash
cratedigger enrich ~/Music/Library/ --only chapter_artist_mbids,album_artist_mbids
```

No `--regenerate` needed. CrateDigger detects that the resolved ID has changed and writes the update automatically.

---

## See also

- [enrich: chapter_artist_mbids](commands/enrich.md#chapter_artist_mbids-per-track-artist-ids): per-chapter MBID resolution and fix workflow
- [enrich: album_artist_mbids](commands/enrich.md#album_artist_mbids-set-level-artist-ids): album-level MBID resolution
- [1001Tracklists integration](tracklists.md): how identify extracts per-chapter metadata
- [Configuration: artist MBID override file](configuration.md#artist-mbid-override-file): user-curated MBID overrides
- [Kodi integration](kodi-integration.md): how these tags surface in Kodi
